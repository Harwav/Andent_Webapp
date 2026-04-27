from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import requests


def latest_print_job(database_path: Path) -> dict:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM print_jobs ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise LookupError("No print job rows found.")

    case_ids = json.loads(row["case_ids"]) if row["case_ids"] else []
    preset_names = json.loads(row["preset_names_json"]) if row["preset_names_json"] else []
    manifest_json = json.loads(row["manifest_json"]) if row["manifest_json"] else None
    return {
        "job_name": row["job_name"],
        "scene_id": row["scene_id"],
        "print_job_id": row["print_job_id"],
        "status": row["status"],
        "preset": row["preset"],
        "preset_names": preset_names,
        "compatibility_key": row["compatibility_key"],
        "case_ids": case_ids,
        "manifest_json": manifest_json,
    }


def parse_health_response(payload: dict) -> dict:
    version = str(payload.get("version", "")).strip()
    return {"ok": bool(version), "version": version}


def check_preform_health(base_url: str) -> dict:
    response = requests.get(f"{base_url.rstrip('/')}/", timeout=10)
    response.raise_for_status()
    return parse_health_response(response.json())


def check_scene(base_url: str, scene_id: str) -> dict:
    response = requests.get(f"{base_url.rstrip('/')}/scene/{scene_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    latest = subparsers.add_parser("latest-print-job")
    latest.add_argument("--database-path", required=True)

    health = subparsers.add_parser("preform-health")
    health.add_argument("--base-url", required=True)

    scene = subparsers.add_parser("scene")
    scene.add_argument("--base-url", required=True)
    scene.add_argument("--scene-id", required=True)

    args = parser.parse_args()

    if args.command == "latest-print-job":
        print(json.dumps(latest_print_job(Path(args.database_path))))
    elif args.command == "preform-health":
        print(json.dumps(check_preform_health(args.base_url)))
    else:
        print(json.dumps(check_scene(args.base_url, args.scene_id)))


if __name__ == "__main__":
    main()
