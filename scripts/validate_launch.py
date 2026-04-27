#!/usr/bin/env python3
"""
Live launch validation script.

Usage:
    python scripts/validate_launch.py [--base-url http://127.0.0.1:8090] [--fixtures-dir Andent/04_customer-facing]

Uploads every .stl file found under fixtures-dir, then fetches
/api/metrics/launch-check and prints a pass/fail report.

PreFormServer is started automatically via the Andent Web managed-install API
if it is not already running. If no managed install exists, validation proceeds
without dispatch proof and the dispatch_success criterion shows vacuously passing.
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
        print("  PreFormServer not installed — skipping dispatch proof.")
        return False

    # installed_not_running or incompatible_version — attempt start
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

    # Reset metrics before the run
    httpx.post(f"{args.base_url}/api/metrics/reset", timeout=10.0).raise_for_status()
    print("Metrics reset.")

    print(f"Uploading to {args.base_url}/api/uploads/classify ...")
    t0 = time.monotonic()
    result = upload_files(args.base_url, stl_files)
    elapsed = time.monotonic() - t0
    print(f"Upload complete: {result.get('file_count', '?')} rows in {elapsed:.1f}s")

    check = get_launch_check(args.base_url)
    overall_pass = print_report(check, preform_running)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
