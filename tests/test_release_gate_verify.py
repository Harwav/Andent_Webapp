"""Release-gate verification helper tests."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from release_gate.helpers.python.release_gate_verify import (
    latest_print_job,
    parse_health_response,
)


def _seed_print_job(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE print_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name TEXT NOT NULL,
                scene_id TEXT,
                print_job_id TEXT,
                status TEXT NOT NULL,
                preset TEXT NOT NULL,
                preset_names_json TEXT,
                compatibility_key TEXT,
                case_ids TEXT,
                manifest_json TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO print_jobs (
                job_name,
                scene_id,
                print_job_id,
                status,
                preset,
                preset_names_json,
                compatibility_key,
                case_ids,
                manifest_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "260421-001",
                "scene-123",
                "print-123",
                "Queued",
                "Ortho Solid - Flat, No Supports",
                json.dumps(["Ortho Solid - Flat, No Supports"]),
                "form-4bl|precision-model-v1|100",
                json.dumps(["CASE123"]),
                json.dumps(
                    {
                        "case_ids": ["CASE123"],
                        "planning_status": "planned",
                        "import_groups": [
                            {
                                "preset_name": "Ortho Solid - Flat, No Supports",
                                "preform_hint": "ortho_solid_v1",
                                "files": [
                                    {
                                        "file_name": "20260409_CASE123_UnsectionedModel_UpperJaw.stl",
                                        "preform_hint": "ortho_solid_v1",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                "2026-04-21T10:00:00Z",
                "2026-04-21T10:00:00Z",
            ),
        )
        connection.commit()


def test_latest_print_job_returns_decoded_manifest_fields(tmp_path):
    database_path = tmp_path / "gate.db"
    _seed_print_job(database_path)

    job = latest_print_job(database_path)

    assert job["job_name"] == "260421-001"
    assert job["scene_id"] == "scene-123"
    assert job["preset_names"] == ["Ortho Solid - Flat, No Supports"]
    assert job["case_ids"] == ["CASE123"]
    assert job["manifest_json"]["planning_status"] == "planned"


def test_parse_health_response_prefers_explicit_version_key():
    parsed = parse_health_response({"status": "ok", "version": "3.57.2.624"})

    assert parsed == {"healthy": True, "version": "3.57.2.624"}


def test_parse_health_response_extracts_version_from_free_text():
    parsed = parse_health_response("PreFormServer build 3.57.2.624 is healthy")

    assert parsed == {"healthy": True, "version": "3.57.2.624"}
