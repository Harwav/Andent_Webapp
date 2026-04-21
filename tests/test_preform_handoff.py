"""Phase 1: Task 3 - PreFormServer Handoff Tests (TDD)."""

from __future__ import annotations

import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from app.config import build_settings
from app.database import get_upload_row_by_id, init_db, list_print_jobs, persist_upload_session
from app.main import create_app


class StubPreFormClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.created_scenes: list[tuple[str, str]] = []
        self.imported_models: list[tuple[str, str, str | None]] = []
        self.print_jobs: list[tuple[str, str]] = []
        self.closed = False

    def create_scene(self, patient_id: str, case_name: str):
        self.created_scenes.append((patient_id, case_name))
        return {"scene_id": f"scene-{len(self.created_scenes)}"}

    def import_model(self, scene_id: str, stl_path: str, preset: str | None = None):
        self.imported_models.append((scene_id, stl_path, preset))
        return {"model_id": f"model-{len(self.imported_models)}"}

    def send_to_printer(self, scene_id: str, device_id: str):
        self.print_jobs.append((scene_id, device_id))
        return {"print_id": f"print-{len(self.print_jobs)}"}

    def close(self):
        self.closed = True


def _build_settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    return build_settings(data_dir=data_dir, database_path=data_dir / "andent_web.db")


def _seed_rows(settings, rows: list[dict]) -> list[int]:
    session_id = f"session-{datetime.now(timezone.utc).timestamp():.0f}"
    init_db(settings)
    persisted = persist_upload_session(settings, session_id, rows)
    return [row.row_id for row in persisted if row.row_id is not None]


def _row_payload(
    file_path: Path,
    *,
    case_id: str,
    preset: str,
    status: str,
    content_hash: str,
    printer: str | None = None,
) -> dict:
    return {
        "file_name": file_path.name,
        "stored_path": str(file_path),
        "content_hash": content_hash,
        "thumbnail_svg": None,
        "case_id": case_id,
        "model_type": "Ortho - Solid",
        "preset": preset,
        "confidence": "high",
        "status": status,
        "dimension_x_mm": None,
        "dimension_y_mm": None,
        "dimension_z_mm": None,
        "volume_ml": None,
        "structure": None,
        "structure_confidence": None,
        "structure_reason": None,
        "structure_metrics_json": None,
        "structure_locked": False,
        "review_required": status != "Ready",
        "review_reason": None,
        "printer": printer,
        "person": None,
    }


def test_send_to_print_creates_preform_batches_and_print_job_records(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_files = [
        tmp_path / "case-1.stl",
        tmp_path / "case-2.stl",
        tmp_path / "case-3.stl",
        tmp_path / "case-4.stl",
    ]
    for idx, file_path in enumerate(case_files, start=1):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")

    row_ids = _seed_rows(
        settings,
        [
            _row_payload(case_files[0], case_id="CASE001", preset="Preset A", status="Ready", content_hash="hash-1"),
            _row_payload(case_files[1], case_id="CASE002", preset="Preset A", status="Ready", content_hash="hash-2"),
            _row_payload(case_files[2], case_id="CASE003", preset="Preset B", status="Ready", content_hash="hash-3"),
            _row_payload(case_files[3], case_id="CASE004", preset="Preset A", status="Check", content_hash="hash-4"),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    assert stub_client.base_url == settings.preform_server_url
    assert len(stub_client.created_scenes) == 2
    assert len(stub_client.imported_models) == 3
    assert len(stub_client.print_jobs) == 2

    submitted_rows = {row["file_name"]: row["status"] for row in response.json()}
    assert submitted_rows["case-1.stl"] == "Submitted"
    assert submitted_rows["case-2.stl"] == "Submitted"
    assert submitted_rows["case-3.stl"] == "Submitted"
    assert submitted_rows["case-4.stl"] == "Check"

    jobs = list_print_jobs(settings)
    assert len(jobs) == 2
    jobs_by_preset = {job.preset: job for job in jobs}
    assert jobs_by_preset["Preset A"].case_ids == ["CASE001", "CASE002"]
    assert jobs_by_preset["Preset B"].case_ids == ["CASE003"]


def test_send_to_print_passes_preset_hint_and_selected_printer(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "tooth-1.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE900",
                preset="Tooth - With Supports",
                status="Ready",
                content_hash="hash-900",
                printer="printer_form4_001",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    assert stub_client.imported_models == [("scene-1", str(case_file), "tooth_v1")]
    assert stub_client.print_jobs == [("scene-1", "printer_form4_001")]


def test_send_to_print_returns_502_when_preform_unavailable(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "case-1.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(case_file, case_id="CASE001", preset="Preset A", status="Ready", content_hash="hash-1"),
        ],
    )

    mock_client = Mock()
    mock_client.create_scene.side_effect = Exception("Connection refused")
    mock_client.close.return_value = None

    with patch("app.services.preform_client.PreFormClient", return_value=mock_client):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 502
    assert "Connection refused" in response.json()["detail"]
    assert get_upload_row_by_id(settings, row_ids[0]).status == "Ready"
    assert list_print_jobs(settings) == []
