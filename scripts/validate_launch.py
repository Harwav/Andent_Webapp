#!/usr/bin/env python3
"""
Live launch validation script.

Usage:
    python scripts/validate_launch.py [--base-url http://127.0.0.1:8090] [--fixtures-dir Andent/04_customer-facing]

Uploads every .stl file found under fixtures-dir, sends one ready case to print
when PreFormServer is ready, then fetches /api/metrics/launch-check and prints
a pass/fail report.

PreFormServer is started automatically via the Andent Web managed-install API
if it is not already running. If no managed install exists, validation proceeds
without dispatch proof and the dispatch_success criterion fails.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx


def find_stl_files(fixtures_dir: Path) -> list[Path]:
    return sorted(fixtures_dir.rglob("*.stl"))


def upload_files(base_url: str, stl_files: list[Path]) -> dict:
    url = f"{base_url}/api/uploads/classify"
    files = [("files", (f.name, f.read_bytes(), "model/stl")) for f in stl_files]
    resp = httpx.post(url, files=files, timeout=120.0)
    resp.raise_for_status()
    return resp.json()


def get_launch_check(base_url: str) -> dict:
    resp = httpx.get(f"{base_url}/api/metrics/launch-check", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def select_dispatch_row_ids(upload_result: dict) -> list[int]:
    ready_rows = [
        row
        for row in upload_result.get("rows", [])
        if row.get("status") == "Ready" and row.get("row_id") is not None
    ]
    rows_by_case: dict[str, list[dict]] = {}
    for row in ready_rows:
        case_id = str(row.get("case_id") or "")
        if case_id:
            rows_by_case.setdefault(case_id, []).append(row)

    grouped_candidates = [
        rows for rows in rows_by_case.values()
        if len(rows) > 1
    ]
    if grouped_candidates:
        return [int(row["row_id"]) for row in grouped_candidates[0]]
    if ready_rows:
        return [int(ready_rows[0]["row_id"])]
    return []


def dispatch_ready_rows(base_url: str, row_ids: list[int]) -> list[dict]:
    resp = httpx.post(
        f"{base_url}/api/uploads/rows/send-to-print",
        json={"row_ids": row_ids},
        timeout=180.0,
    )
    resp.raise_for_status()
    return resp.json()


def clear_active_rows(base_url: str) -> int:
    resp = httpx.get(f"{base_url}/api/uploads/queue", timeout=30.0)
    resp.raise_for_status()
    active = resp.json().get("active_rows", [])
    deletable = [
        row["row_id"]
        for row in active
        if row.get("row_id") and row.get("status") not in ("Submitted", "Locked")
    ]
    if not deletable:
        return 0
    del_resp = httpx.post(
        f"{base_url}/api/uploads/rows/bulk-delete",
        json={"row_ids": deletable},
        timeout=30.0,
    )
    del_resp.raise_for_status()
    return len(del_resp.json().get("deleted_row_ids", []))


def get_print_jobs(base_url: str) -> dict:
    resp = httpx.get(f"{base_url}/api/print-queue/jobs", timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def has_scene_dispatch_evidence(print_jobs: dict) -> bool:
    return any(job.get("scene_id") for job in print_jobs.get("jobs", []))


def ensure_preform_running(base_url: str) -> bool:
    """Start PreFormServer via the managed API if not already running.

    Returns True if PreFormServer is ready, False if unavailable/not installed.
    """
    try:
        resp = httpx.get(f"{base_url}/api/preform-setup/status", timeout=10.0)
        resp.raise_for_status()
        status = resp.json()
    except Exception as exc:
        print(f"  WARNING: could not reach preform-setup status endpoint: {exc}")
        return False

    readiness = status.get("readiness", "")

    if readiness == "ready":
        version = status.get("detected_version", "unknown")
        print(f"  PreFormServer already running (version {version}).")
        return True

    if readiness == "not_installed":
        print("  PreFormServer not installed - skipping dispatch proof.")
        return False

    # installed_not_running or incompatible_version - attempt start
    print(f"  PreFormServer status: {readiness}. Attempting start ...")
    try:
        start_resp = httpx.post(f"{base_url}/api/preform-setup/start", timeout=60.0)
        start_resp.raise_for_status()
        result = start_resp.json()
        new_readiness = result.get("status", {}).get("readiness", "")
        if new_readiness == "ready":
            version = result.get("status", {}).get("detected_version", "unknown")
            print(f"  PreFormServer started successfully (version {version}).")
            return True
        print(f"  PreFormServer start returned readiness={new_readiness!r} -- dispatch proof may be incomplete.")
        return False
    except Exception as exc:
        print(f"  WARNING: could not start PreFormServer: {exc}")
        return False


def print_report(check: dict, preform_running: bool) -> bool:
    """Print the launch report. Returns True if overall_pass."""
    print("\n" + "=" * 60)
    print("  ANDENT WEB -- LAUNCH VALIDATION REPORT")
    print("=" * 60)

    criteria = [
        ("straight_through", "Straight-through rate", ">=", "%"),
        ("review_rate", "Human review rate", "<=", "%"),
        ("latency_p95", "Upload p95 latency", "<=", "s"),
        ("dispatch_success", "Dispatch success rate", ">=", "%"),
    ]

    for key, label, direction, unit in criteria:
        item = check.get(key, {})
        value = item.get("value", "N/A")
        target = item.get("target", "N/A")
        passed = item.get("pass", False)
        icon = "[PASS]" if passed else "[FAIL]"
        if isinstance(value, float):
            value_str = f"{value:.1f}{unit}"
        else:
            value_str = str(value)
        suffix = ""
        if key == "dispatch_success" and not preform_running:
            suffix = " (vacuous -- no PreFormServer)"
        print(f"  {icon}  {label}: {value_str}  (target: {direction}{target}{unit}){suffix}")

    overall = check.get("overall_pass", False)
    print("=" * 60)
    if overall:
        print("  RESULT: [PASS] READY TO SHIP")
    else:
        print("  RESULT: [FAIL] NOT READY -- fix failing criteria above")
    print("=" * 60 + "\n")
    return overall


def main() -> int:
    parser = argparse.ArgumentParser(description="Andent Web launch validation")
    parser.add_argument("--base-url", default="http://127.0.0.1:8090")
    parser.add_argument("--fixtures-dir", default="Andent/04_customer-facing")
    parser.add_argument(
        "--skip-preform",
        action="store_true",
        help="Skip PreFormServer auto-start (classification-only run)",
    )
    args = parser.parse_args()

    fixtures_dir = Path(args.fixtures_dir)
    if not fixtures_dir.exists():
        print(f"ERROR: fixtures dir not found: {fixtures_dir}", file=sys.stderr)
        return 2

    stl_files = find_stl_files(fixtures_dir)
    if not stl_files:
        print(f"ERROR: no .stl files found in {fixtures_dir}", file=sys.stderr)
        return 2

    print(f"Found {len(stl_files)} STL file(s) in {fixtures_dir}")

    # Ensure PreFormServer is running before the validation run
    if args.skip_preform:
        preform_running = False
        print("  Skipping PreFormServer auto-start (--skip-preform).")
    else:
        print("Checking PreFormServer ...")
        preform_running = ensure_preform_running(args.base_url)

    # Clear stale rows to avoid content-hash duplicate detection
    cleared = clear_active_rows(args.base_url)
    if cleared:
        print(f"Cleared {cleared} stale row(s) before validation run.")

    # Reset metrics before the run
    httpx.post(f"{args.base_url}/api/metrics/reset", timeout=10.0).raise_for_status()
    print("Metrics reset.")

    print(f"Uploading to {args.base_url}/api/uploads/classify ...")
    t0 = time.monotonic()
    result = upload_files(args.base_url, stl_files)
    elapsed = time.monotonic() - t0
    print(f"Upload complete: {result.get('file_count', '?')} rows in {elapsed:.1f}s")

    scene_dispatch_proven = False
    if preform_running:
        row_ids = select_dispatch_row_ids(result)
        if not row_ids:
            print("ERROR: no Ready rows available for dispatch proof.", file=sys.stderr)
            return 1
        print(f"Sending {len(row_ids)} ready row(s) to print for dispatch proof ...")
        dispatch_result = dispatch_ready_rows(args.base_url, row_ids)
        print(f"Dispatch request returned {len(dispatch_result)} row(s).")
        print_jobs = get_print_jobs(args.base_url)
        scene_dispatch_proven = has_scene_dispatch_evidence(print_jobs)
        if not scene_dispatch_proven:
            print("ERROR: dispatch did not produce a print job with scene_id.", file=sys.stderr)

    check = get_launch_check(args.base_url)
    overall_pass = print_report(check, preform_running)
    return 0 if overall_pass and scene_dispatch_proven else 1


if __name__ == "__main__":
    sys.exit(main())
