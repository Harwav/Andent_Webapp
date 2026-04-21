from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import requests


def parse_health_response(payload: object) -> dict[str, object]:
    version = _extract_version(payload)
    return {
        "healthy": True,
        "version": version,
    }


def latest_print_job(database_path: Path | str) -> dict[str, Any]:
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT *
            FROM print_jobs
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise RuntimeError("No print jobs found.")

    return {
        "id": row["id"],
        "job_name": row["job_name"],
        "scene_id": row["scene_id"],
        "print_job_id": row["print_job_id"],
        "status": row["status"],
        "preset": row["preset"],
        "preset_names": _loads_list(row["preset_names_json"]),
        "compatibility_key": row["compatibility_key"],
        "case_ids": _loads_list(row["case_ids"]),
        "manifest_json": _loads_dict(row["manifest_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def fetch_scene(base_url: str, scene_id: str) -> dict[str, Any]:
    response = requests.get(
        f"{base_url.rstrip('/')}/scene/{scene_id}",
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and "scene_id" not in payload and "id" in payload:
        payload = {
            **payload,
            "scene_id": payload["id"],
        }
    return payload


def fetch_health(base_url: str) -> dict[str, object]:
    candidates = ["/", "/health", "/health/ready"]
    last_error: Exception | None = None
    for path in candidates:
        try:
            response = requests.get(f"{base_url.rstrip('/')}{path}", timeout=10)
            response.raise_for_status()
            return parse_health_response(_json_or_text(response))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("Health check did not produce a result.")


def _json_or_text(response: requests.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return response.text


def _extract_version(payload: object) -> str | None:
    if isinstance(payload, dict):
        for key in ("version", "build_version", "preform_version", "server_version"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in payload.values():
            detected = _extract_version(value)
            if detected:
                return detected
        return None
    if isinstance(payload, list):
        for item in payload:
            detected = _extract_version(item)
            if detected:
                return detected
        return None
    if isinstance(payload, str):
        match = re.search(r"\d+\.\d+\.\d+(?:\.\d+)?", payload)
        return match.group(0) if match else None
    return None


def _loads_list(value: str | None) -> list[Any]:
    if not value:
        return []
    loaded = json.loads(value)
    return loaded if isinstance(loaded, list) else []


def _loads_dict(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    latest_job_parser = subparsers.add_parser("latest-print-job")
    latest_job_parser.add_argument("--database-path", required=True)

    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--base-url", required=True)

    scene_parser = subparsers.add_parser("scene")
    scene_parser.add_argument("--base-url", required=True)
    scene_parser.add_argument("--scene-id", required=True)

    args = parser.parse_args()

    if args.command == "latest-print-job":
        result = latest_print_job(Path(args.database_path))
    elif args.command == "health":
        result = fetch_health(args.base_url)
    else:
        result = fetch_scene(args.base_url, args.scene_id)

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
