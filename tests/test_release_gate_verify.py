import json
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from release_gate.helpers.python.release_gate_verify import (
    check_scene,
    latest_print_job,
    parse_health_response,
)


def test_latest_print_job_returns_manifest_handoff_evidence(tmp_path):
    db_path = tmp_path / "andent_web.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE print_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name TEXT NOT NULL UNIQUE,
            scene_id TEXT,
            print_job_id TEXT,
            status TEXT NOT NULL,
            preset TEXT NOT NULL,
            preset_names_json TEXT,
            compatibility_key TEXT,
            case_ids TEXT,
            manifest_json TEXT,
            created_at TEXT,
            updated_at TEXT,
            screenshot_url TEXT,
            printer_type TEXT,
            resin TEXT,
            layer_height_microns INTEGER,
            estimated_completion TEXT,
            error_message TEXT
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
            "form-4bl|precision-model-resin|100",
            json.dumps(["CASE123"]),
            json.dumps(
                {
                    "case_ids": ["CASE123"],
                    "preset_names": ["Ortho Solid - Flat, No Supports"],
                    "compatibility_key": "form-4bl|precision-model-resin|100",
                    "import_groups": [
                        {
                            "preset_name": "Ortho Solid - Flat, No Supports",
                            "preform_hint": "ortho_solid_v1",
                            "row_ids": [1],
                            "files": [
                                {
                                    "row_id": 1,
                                    "case_id": "CASE123",
                                    "file_name": "20260409_CASE123_UnsectionedModel_UpperJaw.stl",
                                    "file_path": "data/uploads/session/20260409_CASE123_UnsectionedModel_UpperJaw.stl",
                                    "preset_name": "Ortho Solid - Flat, No Supports",
                                    "preform_hint": "ortho_solid_v1",
                                    "compatibility_key": "form-4bl|precision-model-resin|100",
                                    "xy_footprint_estimate": 100.0,
                                    "support_inflation_factor": 1.0,
                                    "order": 0,
                                }
                            ],
                        }
                    ],
                    "planning_status": "planned",
                    "non_plannable_reason": None,
                }
            ),
            "2026-04-21T00:00:00Z",
            "2026-04-21T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()

    job = latest_print_job(db_path)

    assert job["scene_id"] == "scene-123"
    assert job["print_job_id"] == "print-123"
    assert job["case_ids"] == ["CASE123"]
    assert job["preset_names"] == ["Ortho Solid - Flat, No Supports"]
    assert job["compatibility_key"] == "form-4bl|precision-model-resin|100"
    assert job["manifest_json"]["planning_status"] == "planned"
    assert job["manifest_json"]["import_groups"][0]["files"][0]["preform_hint"] == "ortho_solid_v1"


def test_parse_health_response_accepts_preform_version_payload():
    payload = {"version": "3.57.2.624"}
    parsed = parse_health_response(payload)
    assert parsed["ok"] is True
    assert parsed["version"] == "3.57.2.624"


def test_check_scene_normalizes_preform_id_payload(monkeypatch):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "scene-123", "models": []}

    monkeypatch.setattr(
        "release_gate.helpers.python.release_gate_verify.requests.get",
        lambda *args, **kwargs: _Response(),
    )

    scene = check_scene("http://preform.test", "scene-123")

    assert scene["scene_id"] == "scene-123"
