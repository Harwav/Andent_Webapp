"""Phase 1: Task 3 - PreFormServer Handoff Tests (TDD)."""

from __future__ import annotations

import sys
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from app.config import build_settings
from app.database import (
    connect,
    create_print_job,
    get_upload_row_by_id,
    init_db,
    list_print_jobs,
    persist_upload_session,
)
from app.main import create_app
from app.schemas import PreFormSetupStatus, PrintJob
from tests.conftest import register_test_dims


class StubPreFormClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.created_scenes: list[tuple[str, str]] = []
        self.imported_models: list[tuple[str, str, str | None]] = []
        self.layout_calls: list[str] = []
        self.layout_errors: list[Exception] = []
        self.support_calls: list[tuple[str, object]] = []
        self.validation_results: list[dict[str, object]] = []
        self.validation_calls: list[str] = []
        self.saved_forms: list[tuple[str, str]] = []
        self.saved_screenshots: list[tuple[str, str]] = []
        self.fail_screenshot = False
        self.devices: list[dict[str, object]] = []
        self.device_list_calls = 0
        self.print_jobs: list[tuple[str, str, str | None]] = []
        self.closed = False

    def create_scene(self, patient_id: str, case_name: str, scene_settings: dict | None = None):
        self.created_scenes.append((patient_id, case_name))
        return {"scene_id": f"scene-{len(self.created_scenes)}"}

    def import_model(self, scene_id: str, stl_path: str, preset: str | None = None):
        self.imported_models.append((scene_id, stl_path, preset))
        return {"model_id": f"model-{len(self.imported_models)}"}

    def auto_layout(self, scene_id: str):
        self.layout_calls.append(scene_id)
        if self.layout_errors:
            raise self.layout_errors.pop(0)
        return {"status": "ok"}

    def auto_support(self, scene_id: str, models: object = "ALL"):
        self.support_calls.append((scene_id, models))
        return {"status": "ok"}

    def validate_scene(self, scene_id: str):
        self.validation_calls.append(scene_id)
        if self.validation_results:
            return self.validation_results.pop(0)
        return {"valid": True, "errors": []}

    def save_form(self, scene_id: str, output_path: Path):
        self.saved_forms.append((scene_id, str(Path(output_path).resolve())))
        return {"status": "ok"}

    def save_screenshot(self, scene_id: str, output_path: Path):
        self.saved_screenshots.append((scene_id, str(Path(output_path).resolve())))
        if self.fail_screenshot:
            raise Exception("screenshot unavailable")
        Path(output_path).write_bytes(b"preform-screenshot-png")
        return {"status": "ok"}

    def list_devices(self):
        self.device_list_calls += 1
        return self.devices

    def send_to_printer(self, scene_id: str, device_id: str, job_name: str | None = None):
        self.print_jobs.append((scene_id, device_id, job_name))
        return {"print_id": f"print-{len(self.print_jobs)}"}

    def close(self):
        self.closed = True


class ImportFailurePreFormClient(StubPreFormClient):
    def __init__(self, base_url: str, failing_name_part: str):
        super().__init__(base_url)
        self.failing_name_part = failing_name_part

    def import_model(self, scene_id: str, stl_path: str, preset: str | None = None):
        if self.failing_name_part in Path(stl_path).name:
            raise Exception(
                'Failed to import model: 400 - {"error":{"code":"OPERATION_FAILED","message":"Broken model, the model is damaged and needs repair."}}'
            )
        return super().import_model(scene_id, stl_path, preset)


class DispatchFailurePreFormClient(StubPreFormClient):
    def send_to_printer(self, scene_id: str, device_id: str, job_name: str | None = None):
        raise Exception("printer dispatch failed")


def _build_settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    return replace(
        build_settings(data_dir=data_dir, database_path=data_dir / "formflow.db"),
        output_dir=tmp_path / "output",
        print_hold_density_target=0.0,
        preform_validation_enabled=True,
    )


def _build_holding_settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    return replace(
        build_settings(data_dir=data_dir, database_path=data_dir / "formflow.db"),
        output_dir=tmp_path / "output",
        print_hold_density_target=0.40,
        print_hold_cutoff_local_time="23:59",
    )


def _build_virtual_settings(tmp_path: Path):
    return replace(_build_settings(tmp_path), print_dispatch_mode="virtual")


def _build_virtual_settings_without_validation(tmp_path: Path):
    return replace(_build_virtual_settings(tmp_path), preform_validation_enabled=False)


def _seed_rows(settings, rows: list[dict]) -> list[int]:
    session_id = f"session-{uuid4().hex}"
    init_db(settings)
    persisted = persist_upload_session(settings, session_id, rows)
    return [row.row_id for row in persisted if row.row_id is not None]


def _ready_setup_status(settings) -> PreFormSetupStatus:
    return PreFormSetupStatus(
        readiness="ready",
        install_path=str(settings.preform_managed_dir),
        managed_executable_path=str(settings.preform_managed_executable),
        detected_version="3.57.2.624",
        expected_version_min=settings.preform_min_supported_version,
        expected_version_max=settings.preform_max_supported_version,
        active_configured_source=True,
        is_running=True,
        last_health_check_at=datetime.now(timezone.utc).isoformat(),
        last_error_code=None,
        last_error_message=None,
    )


def _row_payload(
    file_path: Path,
    *,
    case_id: str,
    preset: str,
    status: str,
    content_hash: str,
    model_type: str = "Ortho - Solid",
    printer: str | None = None,
    dimension_x_mm: float = 40.0,
    dimension_y_mm: float = 30.0,
    dimension_z_mm: float = 10.0,
    volume_ml: float | None = 1.0,
) -> dict:
    return {
        "file_name": file_path.name,
        "stored_path": str(file_path),
        "content_hash": content_hash,
        "thumbnail_svg": None,
        "case_id": case_id,
        "model_type": model_type,
        "preset": preset,
        "confidence": "high",
        "status": status,
        "dimension_x_mm": dimension_x_mm,
        "dimension_y_mm": dimension_y_mm,
        "dimension_z_mm": dimension_z_mm,
        "volume_ml": volume_ml,
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
            _row_payload(
                case_files[0],
                case_id="CASE001",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-1",
                dimension_x_mm=150.0,
                dimension_y_mm=100.0,
            ),
            _row_payload(
                case_files[1],
                case_id="CASE002",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-2",
                dimension_x_mm=140.0,
                dimension_y_mm=100.0,
            ),
            _row_payload(
                case_files[2],
                case_id="CASE003",
                preset="Tooth - With Supports",
                status="Ready",
                content_hash="hash-3",
                model_type="Tooth",
                dimension_x_mm=40.0,
                dimension_y_mm=25.0,
            ),
            _row_payload(
                case_files[3],
                case_id="CASE004",
                preset="Ortho Solid - Flat, No Supports",
                status="Check",
                content_hash="hash-4",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    assert stub_client.base_url == settings.preform_server_url
    assert len(stub_client.created_scenes) == 1
    assert len(stub_client.imported_models) == 3
    assert len(stub_client.layout_calls) == 2
    assert stub_client.support_calls == [("scene-1", ["model-3"])]
    assert stub_client.print_jobs == []

    submitted_rows = {row["file_name"]: row["status"] for row in response.json()}
    assert submitted_rows["case-1.stl"] == "Submitted"
    assert submitted_rows["case-2.stl"] == "Submitted"
    assert submitted_rows["case-3.stl"] == "Submitted"
    assert submitted_rows["case-4.stl"] == "Check"

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    expected_form_path = settings.output_dir / jobs[0].job_name / f"{jobs[0].job_name}.form"
    assert stub_client.saved_forms == [("scene-1", str(expected_form_path.resolve()))]
    assert jobs[0].form_file_path == str(expected_form_path.resolve())
    assert jobs[0].print_job_id is None
    assert jobs[0].case_ids == ["CASE001", "CASE002", "CASE003"]
    assert jobs[0].preset_names == [
        "Ortho Solid - Flat, No Supports",
        "Tooth - With Supports",
    ]


def test_virtual_dispatch_mode_sends_to_preform_virtual_printer_and_records_print_id(tmp_path):
    settings = _build_virtual_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "virtual-case.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-VIRTUAL",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-virtual",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "virtual-device-1", "name": "Virtual Printer", "is_virtual": True}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert stub_client.device_list_calls == 1
    assert stub_client.print_jobs == [
        ("scene-1", "virtual-device-1", jobs[0].job_name)
    ]
    assert jobs[0].print_job_id == "print-1"
    assert jobs[0].screenshot_url == f"/api/print-queue/jobs/{jobs[0].id}/screenshot"
    expected_form_path = settings.output_dir / jobs[0].job_name / f"{jobs[0].job_name}.form"
    assert jobs[0].form_file_path == str(expected_form_path.resolve())
    assert response.json()[0]["status"] == "Submitted"

    screenshot_response = client.get(f"/api/print-queue/jobs/{jobs[0].id}/screenshot")

    assert screenshot_response.status_code == 200
    assert screenshot_response.headers["content-type"] == "image/png"
    assert screenshot_response.content == b"preform-screenshot-png"


def test_preview_batches_returns_manifest_assignment_ids(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "preview-case.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-PREVIEW",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-preview",
            ),
        ],
    )

    response = client.post("/api/uploads/rows/preview-batches", json={"row_ids": row_ids})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["groups"]) == 1
    group = payload["groups"][0]
    assert group["row_ids"] == row_ids
    assert group["case_ids"] == ["CASE-PREVIEW"]
    assert group["printer_model"] == "Form 4BL"
    assert group["planning_status"] == "planned"
    assert group["manifest_id"].startswith("form-4bl|")
    assert len(group["manifest_id"].rsplit("|", 1)[-1]) == 16


def test_selected_device_send_to_print_rejects_unknown_device_before_scene_creation(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "unknown-device-case.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-UNKNOWN-DEVICE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-unknown-device",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-east", "name": "Form 4BL East", "model": "Form 4BL", "status": "ready"}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "stale-device"},
        )

    assert response.status_code == 422
    payload = response.json()
    assert "detail" not in payload
    assert payload["blocked_groups"][0]["status"] == "failed"
    assert "stale-device" in payload["blocked_groups"][0]["error"]
    assert stub_client.created_scenes == []
    assert stub_client.print_jobs == []
    assert list_print_jobs(settings) == []
    assert get_upload_row_by_id(settings, row_ids[0]).status == "Ready"


def test_selected_device_send_to_print_rejects_unsupported_virtual_printer_before_scene_creation(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "unsupported-virtual-case.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-UNSUPPORTED-VIRTUAL",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-unsupported-virtual",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4", "name": "Form 4", "model": "Form 4", "status": "Virtual Printer", "is_virtual": True}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4"},
        )

    assert response.status_code == 422
    payload = response.json()
    assert payload["blocked_groups"][0]["status"] == "failed"
    assert "Form 4" in payload["blocked_groups"][0]["error"]
    assert stub_client.created_scenes == []
    assert stub_client.print_jobs == []
    assert list_print_jobs(settings) == []
    assert get_upload_row_by_id(settings, row_ids[0]).status == "Ready"


def test_selected_device_send_to_print_dispatches_to_selected_real_device_and_records_device(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "selected-real-case.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-REAL",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-real",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-east", "name": "Form 4BL East", "model": "Form 4BL", "status": "ready"}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4bl-east"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["groups"][0]["status"] == "submitted"
    assert payload["groups"][0]["row_ids"] == row_ids
    assert payload["quarantined_cases"] == []
    assert payload["blocked_groups"] == []
    assert isinstance(payload["prevalidation_ms"], int)
    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert stub_client.print_jobs == [("scene-1", "form-4bl-east", jobs[0].job_name)]
    assert jobs[0].print_job_id == "print-1"
    assert jobs[0].printer_device_id == "form-4bl-east"
    assert jobs[0].printer_device_name == "Form 4BL East"


def test_selected_device_send_to_print_reserves_job_before_preform_side_effects(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "reserved-before-preform.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-RESERVE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-reserve-before-preform",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-east", "name": "Form 4BL East", "model": "Form 4BL", "status": "ready"}
    ]
    original_create_scene = stub_client.create_scene
    reservation_seen = {"value": False}

    def create_scene_after_reservation_check(patient_id, case_name, scene_settings=None):
        jobs = list_print_jobs(settings)
        row = get_upload_row_by_id(settings, row_ids[0])
        reservation_seen["value"] = (
            len(jobs) == 1
            and jobs[0].job_name == case_name
            and row.status == "Submitted"
            and row.queue_section == "in_progress"
            and row.handoff_stage == "Processing"
            and row.linked_print_job_id == jobs[0].id
        )
        return original_create_scene(patient_id, case_name, scene_settings)

    stub_client.create_scene = create_scene_after_reservation_check
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4bl-east"},
        )

    assert response.status_code == 200
    assert reservation_seen["value"] is True
    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].scene_id == "scene-1"
    assert jobs[0].print_job_id == "print-1"


def test_selected_device_preform_connection_failure_cleans_reservation(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "selected-connection-failure.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-CONNECTION-FAIL",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-selected-connection-failure",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-east", "name": "Form 4BL East", "model": "Form 4BL", "status": "ready"}
    ]
    stub_client.create_scene = Mock(side_effect=Exception("Connection reset"))
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4bl-east"},
        )

    assert response.status_code == 502
    assert "Connection reset" in response.json()["detail"]
    row = get_upload_row_by_id(settings, row_ids[0])
    assert row.status == "Ready"
    assert row.queue_section == "analysis"
    assert row.handoff_stage is None
    assert row.linked_print_job_id is None
    assert list_print_jobs(settings) == []


def test_save_form_send_to_print_reserves_job_before_preform_side_effects(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "save-form-reserved-before-preform.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-SAVE-RESERVE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-save-reserve-before-preform",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    original_create_scene = stub_client.create_scene
    reservation_seen = {"value": False}

    def create_scene_after_reservation_check(patient_id, case_name, scene_settings=None):
        jobs = list_print_jobs(settings)
        row = get_upload_row_by_id(settings, row_ids[0])
        reservation_seen["value"] = (
            len(jobs) == 1
            and jobs[0].job_name == case_name
            and row.status == "Submitted"
            and row.queue_section == "in_progress"
            and row.handoff_stage == "Processing"
            and row.linked_print_job_id == jobs[0].id
        )
        return original_create_scene(patient_id, case_name, scene_settings)

    stub_client.create_scene = create_scene_after_reservation_check
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids},
        )

    assert response.status_code == 200
    assert reservation_seen["value"] is True
    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].scene_id == "scene-1"
    assert jobs[0].print_job_id is None


def test_selected_device_send_to_print_quarantines_bad_case_and_dispatches_remaining_case(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    bad_upper = tmp_path / "bad-upper.stl"
    bad_lower = tmp_path / "bad-lower.stl"
    good_file = tmp_path / "good-case.stl"
    for file_path in (bad_upper, bad_lower, good_file):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                bad_upper,
                case_id="CASE-BAD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-bad-upper",
            ),
            _row_payload(
                bad_lower,
                case_id="CASE-BAD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-bad-lower",
            ),
            _row_payload(
                good_file,
                case_id="CASE-GOOD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-good",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-east", "name": "Form 4BL East", "model": "Form 4BL", "status": "ready"}
    ]
    def validate_side_effect(path):
        if Path(path).name == "bad-upper.stl":
            return Mock(is_valid=False, message="Corrupted STL file: bad-upper.stl - parse error")
        return Mock(is_valid=True, message="OK")

    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", side_effect=validate_side_effect):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4bl-east"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["groups"][0]["row_ids"] == [row_ids[2]]
    assert payload["quarantined_cases"] == [
        {
            "case_id": "CASE-BAD",
            "row_ids": row_ids[:2],
            "reason": "bad-upper.stl - Corrupted STL file: bad-upper.stl - parse error",
        }
    ]
    assert get_upload_row_by_id(settings, row_ids[0]).status == "Needs Review"
    assert get_upload_row_by_id(settings, row_ids[1]).status == "Needs Review"
    assert get_upload_row_by_id(settings, row_ids[2]).status == "Submitted"
    assert stub_client.imported_models == [("scene-1", str(good_file), "ortho_solid_v1")]


def test_import_quarantine_recomputes_manifest_density_for_accepted_cases(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    accepted_file = tmp_path / "accepted.stl"
    broken_file = tmp_path / "broken.stl"
    for file_path in (accepted_file, broken_file):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(accepted_file), 40.0, 30.0)
    register_test_dims(str(broken_file), 50.0, 40.0)

    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                accepted_file,
                case_id="CASE-ACCEPTED",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-accepted",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
            _row_payload(
                broken_file,
                case_id="CASE-BROKEN",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-broken",
                dimension_x_mm=50.0,
                dimension_y_mm=40.0,
            ),
        ],
    )

    stub_client = ImportFailurePreFormClient(settings.preform_server_url, "broken.stl")
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].case_ids == ["CASE-ACCEPTED"]
    assert jobs[0].estimated_density == 1200.0 / 69188.0
    assert jobs[0].manifest_json["used_xy_budget"] == 1200.0
    assert jobs[0].manifest_json["estimated_density"] == 1200.0 / 69188.0

    broken_row = get_upload_row_by_id(settings, row_ids[1])
    assert broken_row is not None
    assert broken_row.status == "Needs Review"
    assert "Broken model" in (broken_row.review_reason or "")


def test_build_lane_key_merges_compatible_presets_in_same_material_lane(tmp_path):
    from app.database import get_upload_row_by_id
    from app.services.build_planning import plan_build_manifests
    from app.services.print_queue_service import _build_lane_keys_from_manifests

    settings = _build_settings(tmp_path)
    model_file = tmp_path / "model.stl"
    tooth_file = tmp_path / "tooth.stl"
    for file_path in (model_file, tooth_file):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                model_file,
                case_id="CASE-LANE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-lane-model",
            ),
            _row_payload(
                tooth_file,
                case_id="CASE-LANE",
                preset="Tooth - With Supports",
                status="Ready",
                content_hash="hash-lane-tooth",
                model_type="Tooth",
            ),
        ],
    )
    rows = [get_upload_row_by_id(settings, row_id) for row_id in row_ids]
    manifests = plan_build_manifests(rows)

    lane_keys = _build_lane_keys_from_manifests(manifests)

    assert len(lane_keys) == 1
    assert "form 4bl" in lane_keys[0]
    assert "precision model" in lane_keys[0]
    assert "|100|" in lane_keys[0]


def test_build_lane_key_splits_selected_devices_for_same_material_lane(tmp_path):
    from app.database import get_upload_row_by_id
    from app.services.build_planning import plan_build_manifests
    from app.services.print_queue_service import _build_lane_keys_from_manifests

    settings = _build_settings(tmp_path)
    case_file = tmp_path / "device-lane.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-DEVICE-LANE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-lane",
            ),
        ],
    )
    rows = [get_upload_row_by_id(settings, row_ids[0])]
    manifests = plan_build_manifests(rows)

    east = _build_lane_keys_from_manifests(manifests, device_id="form-4bl-east")
    west = _build_lane_keys_from_manifests(manifests, device_id="form-4bl-west")

    assert east != west
    assert east[0].startswith("device:form-4bl-east|")
    assert west[0].startswith("device:form-4bl-west|")


def test_send_to_print_holds_rows_when_same_build_lane_is_busy(tmp_path):
    from app.database import get_upload_row_by_id, try_acquire_build_lane_lock
    from app.services.build_planning import plan_build_manifests
    from app.services.print_queue_service import _build_lane_keys_from_manifests

    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "busy-lane.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-BUSY-LANE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-busy-lane",
            ),
        ],
    )
    rows = [get_upload_row_by_id(settings, row_ids[0])]
    lane_key = _build_lane_keys_from_manifests(
        plan_build_manifests(rows),
        device_id="form-4bl-lab",
    )[0]
    assert try_acquire_build_lane_lock(settings, lane_key, "test-owner", "send")

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {
            "id": "form-4bl-lab",
            "name": "Lab Printer",
            "model": "Form 4BL",
            "status": "Ready",
            "is_virtual": True,
        }
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4bl-lab"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["groups"][0]["status"] == "held"
    assert "already preparing" in payload["groups"][0]["error"].lower()
    assert stub_client.imported_models == []
    assert stub_client.print_jobs == []

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].status == "Holding for More Cases"
    assert jobs[0].printer_device_id == "form-4bl-lab"
    assert jobs[0].case_ids == ["CASE-BUSY-LANE"]

    row = get_upload_row_by_id(settings, row_ids[0])
    assert row.status == "Submitted"
    assert row.queue_section == "in_progress"
    assert row.handoff_stage == "Holding for More Cases"
    assert row.linked_print_job_id == jobs[0].id

    with closing(connect(settings)) as connection:
        events = connection.execute(
            """
            SELECT event_type, metadata_json
            FROM upload_row_events
            WHERE row_id = ?
            ORDER BY id
            """,
            (row_ids[0],),
        ).fetchall()
    assert [event["event_type"] for event in events] == [
        "created",
        "handoff_started",
        "build_holding",
    ]
    assert not any(event["event_type"] == "handoff_failed" for event in events)


def test_send_to_print_allows_different_material_lane_while_other_lane_locked(tmp_path):
    from app.database import try_acquire_build_lane_lock

    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "unlocked-lane.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-UNLOCKED-LANE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-unlocked-lane",
            ),
        ],
    )

    assert try_acquire_build_lane_lock(
        settings,
        "group:form 4b|form 4b|lt-clear|lt clear|100|default",
        "test-owner",
        "send",
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    assert len(list_print_jobs(settings)) == 1


def test_import_quarantine_holds_accepted_manifest_when_density_drops_below_target(tmp_path):
    settings = _build_holding_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    accepted_file = tmp_path / "accepted-under-target.stl"
    broken_file = tmp_path / "broken-large.stl"
    for file_path in (accepted_file, broken_file):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(accepted_file), 40.0, 30.0)
    register_test_dims(str(broken_file), 700.0, 40.0)

    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                accepted_file,
                case_id="CASE-ACCEPTED-HOLD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-accepted-hold",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
            _row_payload(
                broken_file,
                case_id="CASE-BROKEN-LARGE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-broken-large",
                dimension_x_mm=700.0,
                dimension_y_mm=40.0,
            ),
        ],
    )

    stub_client = ImportFailurePreFormClient(settings.preform_server_url, "broken-large.stl")
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].status == "Holding for More Cases"
    assert jobs[0].hold_reason == "below_density_target"
    assert jobs[0].estimated_density == 1200.0 / 69188.0
    assert jobs[0].case_ids == ["CASE-ACCEPTED-HOLD"]

    accepted_row = get_upload_row_by_id(settings, row_ids[0])
    broken_row = get_upload_row_by_id(settings, row_ids[1])
    assert accepted_row.handoff_stage == "Holding for More Cases"
    assert broken_row.status == "Needs Review"


def test_selected_device_import_quarantine_holds_under_target_without_printer_dispatch(tmp_path):
    settings = _build_holding_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    accepted_file = tmp_path / "device-accepted-under-target.stl"
    broken_file = tmp_path / "device-broken-large.stl"
    for file_path in (accepted_file, broken_file):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(accepted_file), 40.0, 30.0)
    register_test_dims(str(broken_file), 700.0, 40.0)

    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                accepted_file,
                case_id="CASE-DEVICE-ACCEPTED-HOLD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-accepted-hold",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
            _row_payload(
                broken_file,
                case_id="CASE-DEVICE-BROKEN-LARGE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-broken-large",
                dimension_x_mm=700.0,
                dimension_y_mm=40.0,
            ),
        ],
    )

    stub_client = ImportFailurePreFormClient(settings.preform_server_url, "device-broken-large.stl")
    stub_client.devices = [
        {"id": "form-4bl-lab", "name": "Lab Printer", "model": "Form 4BL", "status": "ready"}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4bl-lab"},
        )

    assert response.status_code == 200
    assert stub_client.print_jobs == []
    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].status == "Holding for More Cases"
    assert jobs[0].printer_device_id == "form-4bl-lab"
    assert jobs[0].estimated_density == 1200.0 / 69188.0


def test_selected_device_dispatch_failure_removes_reserved_job(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "device-dispatch-fails.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-DISPATCH-FAILS",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-dispatch-fails",
            ),
        ],
    )

    stub_client = DispatchFailurePreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-lab", "name": "Lab Printer", "model": "Form 4BL", "status": "ready"}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4bl-lab"},
        )

    assert response.status_code == 502
    assert list_print_jobs(settings) == []
    row = get_upload_row_by_id(settings, row_ids[0])
    assert row.status == "Ready"
    assert row.queue_section == "analysis"
    assert row.linked_print_job_id is None


def test_selected_device_send_to_print_marks_import_failure_for_review_without_retry(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "import-fails.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-IMPORT-FAIL",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-import-fail",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-east", "name": "Form 4BL East", "model": "Form 4BL", "status": "ready"}
    ]
    stub_client.import_model = Mock(side_effect=Exception("mesh rejected"))
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4bl-east"},
        )

    assert response.status_code == 502
    payload = response.json()
    assert payload["groups"] == []
    assert payload["blocked_groups"][0]["status"] == "failed"
    assert "PreFormServer rejected every STL" in payload["blocked_groups"][0]["error"]
    assert stub_client.import_model.call_count == 1
    row = get_upload_row_by_id(settings, row_ids[0])
    assert row.status == "Needs Review"
    assert "mesh rejected" in row.review_reason
    assert list_print_jobs(settings) == []


def test_selected_device_empty_import_failure_marks_active_manifest_without_retry(tmp_path):
    from app.services.print_queue_service import PreFormImportFailureError

    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "support-model-id-missing.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-EMPTY-IMPORT-FAIL",
                preset="Tooth - With Supports",
                status="Ready",
                content_hash="hash-empty-import-fail",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-east", "name": "Form 4BL East", "model": "Form 4BL", "status": "ready"}
    ]
    process_manifest = Mock(side_effect=PreFormImportFailureError({}))
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")), patch(
        "app.services.print_queue_service.process_print_manifest",
        process_manifest,
    ):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4bl-east"},
        )

    assert response.status_code == 502
    assert process_manifest.call_count == 1
    payload = response.json()
    assert payload["groups"] == []
    assert payload["blocked_groups"][0]["status"] == "failed"
    row = get_upload_row_by_id(settings, row_ids[0])
    assert row.status == "Needs Review"
    assert "PreForm import failed" in row.review_reason
    assert list_print_jobs(settings) == []


def test_selected_device_import_failure_review_write_retries_transient_sqlite_lock(tmp_path):
    import sqlite3

    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "import-lock-retry.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-LOCK-RETRY",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-import-lock-retry",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-east", "name": "Form 4BL East", "model": "Form 4BL", "status": "ready"}
    ]
    stub_client.import_model = Mock(side_effect=Exception("mesh rejected"))

    original_mark_cases = __import__(
        "app.services.print_queue_service",
        fromlist=["_mark_cases_needs_review"],
    )._mark_cases_needs_review
    calls = {"count": 0}

    def flaky_mark_cases(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return original_mark_cases(*args, **kwargs)

    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")), patch(
        "app.services.print_queue_service._mark_cases_needs_review",
        side_effect=flaky_mark_cases,
    ):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4bl-east"},
        )

    assert response.status_code == 502
    assert calls["count"] == 2
    row = get_upload_row_by_id(settings, row_ids[0])
    assert row.status == "Needs Review"
    assert "mesh rejected" in row.review_reason


def test_save_form_handoff_stores_preform_screenshot_beside_form_file(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "screenshot-case.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-SCREENSHOT",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-screenshot",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    expected_screenshot_path = settings.output_dir / jobs[0].job_name / f"{jobs[0].job_name}.png"
    assert stub_client.saved_screenshots == [
        ("scene-1", str(expected_screenshot_path.resolve()))
    ]
    assert jobs[0].screenshot_url == f"/api/print-queue/jobs/{jobs[0].id}/screenshot"

    screenshot_response = client.get(f"/api/print-queue/jobs/{jobs[0].id}/screenshot")

    assert screenshot_response.status_code == 200
    assert screenshot_response.content == b"preform-screenshot-png"


def test_screenshot_capture_failure_keeps_generated_preview_fallback(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "fallback-case.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-FALLBACK",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-fallback",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.fail_screenshot = True
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    expected_screenshot_path = settings.output_dir / jobs[0].job_name / f"{jobs[0].job_name}.png"
    assert stub_client.saved_screenshots == [
        ("scene-1", str(expected_screenshot_path.resolve()))
    ]
    assert jobs[0].screenshot_url == f"/api/print-queue/jobs/{jobs[0].id}/screenshot"

    from app.services import print_queue_service

    print_queue_service._screenshot_cache.clear()
    screenshot_response = client.get(f"/api/print-queue/jobs/{jobs[0].id}/screenshot")

    assert screenshot_response.status_code == 200
    assert screenshot_response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_virtual_dispatch_accepts_preform_device_wrapper_payload(tmp_path):
    settings = _build_virtual_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "virtual-wrapper-case.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-VIRTUAL-WRAPPED",
                preset="Ortho Solid - Flat, No Supports",
                printer="Form 4BL",
                status="Ready",
                content_hash="hash-virtual-wrapped",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = {
        "count": 2,
        "devices": [
            {"id": "Form 4", "connection_type": "VIRTUAL", "status": "Virtual Printer"},
            {"id": "Form 4BL", "connection_type": "VIRTUAL", "status": "Virtual Printer"},
        ],
    }
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    jobs = list_print_jobs(settings)
    assert stub_client.print_jobs == [("scene-1", "Form 4BL", jobs[0].job_name)]


def test_virtual_dispatch_accepts_preform_json_string_device_payload(tmp_path):
    settings = _build_virtual_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "virtual-string-case.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-VIRTUAL-STRING",
                preset="Ortho Solid - Flat, No Supports",
                printer="Form 4BL",
                status="Ready",
                content_hash="hash-virtual-string",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = (
        '{"count":1,"devices":[{"id":"Form 4BL",'
        '"connection_type":"VIRTUAL","status":"Virtual Printer"}]}'
    )
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    jobs = list_print_jobs(settings)
    assert stub_client.print_jobs == [("scene-1", "Form 4BL", jobs[0].job_name)]


def test_send_to_print_uses_next_daily_sequence_for_today(tmp_path):
    settings = _build_virtual_settings(tmp_path)
    today_prefix = datetime.now().strftime("%y%m%d")
    init_db(settings)
    create_print_job(
        settings,
        PrintJob(
            job_name=f"{today_prefix}_0001",
            preset="Ortho Solid - Flat, No Supports",
            status="Queued",
            case_ids=["CASE-NEXT-JOB"],
        ),
    )

    app = create_app(settings)
    client = TestClient(app)
    case_file = tmp_path / "next-job-name-case.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-NEXT-JOB",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-next-job-name",
                printer="Form 4BL",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "Form 4BL", "connection_type": "VIRTUAL", "status": "Virtual Printer"}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    jobs = list_print_jobs(settings)
    assert [job.job_name for job in jobs] == [
        f"{today_prefix}_0002",
        f"{today_prefix}_0001",
    ]
    assert jobs[0].case_ids == ["CASE-NEXT-JOB"]
    assert stub_client.print_jobs == [("scene-1", "Form 4BL", f"{today_prefix}_0002")]


def test_virtual_dispatch_can_skip_preform_validation_when_disabled(tmp_path):
    settings = _build_virtual_settings_without_validation(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "skip-validation-case.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-SKIP-VALIDATION",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-skip-validation",
                printer="Form 4BL",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "Form 4BL", "connection_type": "VIRTUAL", "status": "Virtual Printer"}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].validation_passed is True
    assert jobs[0].validation_errors == []
    assert stub_client.validation_calls == []
    assert stub_client.print_jobs == [("scene-1", "Form 4BL", jobs[0].job_name)]


def test_virtual_dispatch_mode_refuses_physical_only_devices(tmp_path):
    settings = _build_virtual_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "physical-only.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-PHYSICAL",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-physical",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "real-device-1", "name": "Form 4BL", "is_virtual": False}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 502
    assert "virtual printer" in response.json()["detail"].lower()
    assert stub_client.device_list_calls == 1
    assert stub_client.print_jobs == []
    assert get_upload_row_by_id(settings, row_ids[0]).status == "Ready"
    assert list_print_jobs(settings) == []


def test_invalid_dispatch_mode_fails_settings_load(tmp_path, monkeypatch):
    monkeypatch.setenv("FORMFLOW_WEB_PRINT_DISPATCH_MODE", "unexpected")

    try:
        build_settings(data_dir=tmp_path / "data", database_path=tmp_path / "data" / "formflow.db")
    except ValueError as exc:
        assert "FORMFLOW_WEB_PRINT_DISPATCH_MODE" in str(exc)
    else:
        raise AssertionError("Invalid dispatch mode should fail settings load.")


def test_send_to_print_groups_compatible_mixed_presets_into_one_job(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_a = tmp_path / "case-a.stl"
    case_b = tmp_path / "case-b.stl"
    for file_path in (case_a, case_b):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")

    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_a,
                case_id="CASE-A",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-a",
                dimension_x_mm=60.0,
                dimension_y_mm=50.0,
            ),
            _row_payload(
                case_b,
                case_id="CASE-B",
                preset="Tooth - With Supports",
                status="Ready",
                content_hash="hash-b",
                model_type="Tooth",
                dimension_x_mm=35.0,
                dimension_y_mm=35.0,
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    assert len(stub_client.created_scenes) == 1
    assert stub_client.imported_models == [
        ("scene-1", str(case_a), "ortho_solid_v1"),
        ("scene-1", str(case_b), "tooth_v1"),
    ]
    assert stub_client.support_calls == [("scene-1", ["model-2"])]
    assert stub_client.layout_calls == ["scene-1", "scene-1"]

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].job_name == f"{datetime.now().strftime('%y%m%d')}_0001"
    assert jobs[0].case_ids == ["CASE-A", "CASE-B"]
    assert jobs[0].preset_names == [
        "Ortho Solid - Flat, No Supports",
        "Tooth - With Supports",
    ]
    assert jobs[0].compatibility_key == "form-4bl|precision-model-v1|100"
    assert jobs[0].manifest_json is not None
    assert jobs[0].manifest_json["case_ids"] == ["CASE-A", "CASE-B"]
    expected_form_path = settings.output_dir / jobs[0].job_name / f"{jobs[0].job_name}.form"
    assert stub_client.saved_forms == [("scene-1", str(expected_form_path.resolve()))]
    assert jobs[0].form_file_path == str(expected_form_path.resolve())


def test_send_to_print_records_validation_warnings_without_rollback(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_files = [
        tmp_path / "case-a.stl",
        tmp_path / "case-b.stl",
        tmp_path / "case-c.stl",
    ]
    for file_path in case_files:
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(case_files[0]), 150.0, 100.0, "Tooth")
    register_test_dims(str(case_files[1]), 60.0, 50.0)
    register_test_dims(str(case_files[2]), 140.0, 100.0)

    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_files[0],
                case_id="CASE-TOOTH",
                preset="Tooth - With Supports",
                status="Ready",
                content_hash="hash-tooth",
                model_type="Tooth",
                dimension_x_mm=150.0,
                dimension_y_mm=100.0,
            ),
            _row_payload(
                case_files[1],
                case_id="CASE-ORTHO",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-ortho",
                dimension_x_mm=60.0,
                dimension_y_mm=50.0,
            ),
            _row_payload(
                case_files[2],
                case_id="CASE-LATE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-late",
                dimension_x_mm=140.0,
                dimension_y_mm=100.0,
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.validation_results = [{"valid": False, "errors": ["overlap"]}]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    row_statuses = {row["file_name"]: row["status"] for row in response.json()}
    assert row_statuses["case-a.stl"] == "Submitted"
    assert row_statuses["case-b.stl"] == "Submitted"
    assert row_statuses["case-c.stl"] == "Submitted"
    assert len(stub_client.created_scenes) == 1
    assert stub_client.imported_models == [
        ("scene-1", str(case_files[0]), "tooth_v1"),
        ("scene-1", str(case_files[2]), "ortho_solid_v1"),
        ("scene-1", str(case_files[1]), "ortho_solid_v1"),
    ]
    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    expected_form_path = settings.output_dir / jobs[0].job_name / f"{jobs[0].job_name}.form"
    assert stub_client.saved_forms == [("scene-1", str(expected_form_path.resolve()))]
    assert jobs[0].validation_passed is False
    assert jobs[0].validation_errors == ["overlap"]
    assert jobs[0].case_ids == ["CASE-TOOTH", "CASE-LATE", "CASE-ORTHO"]


def test_auto_layout_fit_failure_removes_smallest_case_and_keeps_sending(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_files = [
        tmp_path / "case-a.stl",
        tmp_path / "case-b.stl",
        tmp_path / "case-c.stl",
    ]
    for file_path in case_files:
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(case_files[0]), 40.0, 30.0, "Ortho - Solid")
    register_test_dims(str(case_files[1]), 10.0, 10.0, "Ortho - Solid")
    register_test_dims(str(case_files[2]), 30.0, 30.0, "Ortho - Solid")

    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_files[0],
                case_id="CASE-A",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-a",
            ),
            _row_payload(
                case_files[1],
                case_id="CASE-B",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-b",
            ),
            _row_payload(
                case_files[2],
                case_id="CASE-C",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-c",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.layout_errors = [
        Exception(
            'Failed to auto-layout scene: 400 - {"error":{"code":"OPERATION_FAILED","message":"The layout tool was unable to fit all of the selected models into the work area."}}'
        )
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    rows_by_case = {row["case_id"]: row for row in response.json()}
    assert rows_by_case["CASE-A"]["queue_section"] == "history"
    assert rows_by_case["CASE-B"]["queue_section"] == "history"
    assert rows_by_case["CASE-C"]["queue_section"] == "history"

    jobs = list_print_jobs(settings)
    assert len(jobs) == 2
    jobs_by_cases = {tuple(job.case_ids): job for job in jobs}
    assert set(jobs_by_cases) == {("CASE-A", "CASE-C"), ("CASE-B",)}
    assert stub_client.created_scenes == [
        ("CASE-A", jobs_by_cases[("CASE-A", "CASE-C")].job_name),
        ("CASE-A", jobs_by_cases[("CASE-A", "CASE-C")].job_name),
        ("CASE-B", jobs_by_cases[("CASE-B",)].job_name),
    ]


def test_selected_device_auto_layout_fit_failure_retries_smaller_manifest(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_files = [
        tmp_path / "device-case-a.stl",
        tmp_path / "device-case-b.stl",
        tmp_path / "device-case-c.stl",
    ]
    for file_path in case_files:
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(case_files[0]), 40.0, 30.0, "Ortho - Solid")
    register_test_dims(str(case_files[1]), 10.0, 10.0, "Ortho - Solid")
    register_test_dims(str(case_files[2]), 30.0, 30.0, "Ortho - Solid")

    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_files[0],
                case_id="CASE-A",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-a",
            ),
            _row_payload(
                case_files[1],
                case_id="CASE-B",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-b",
            ),
            _row_payload(
                case_files[2],
                case_id="CASE-C",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-c",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-lab", "name": "Lab Printer", "model": "Form 4BL", "status": "ready"}
    ]
    stub_client.layout_errors = [
        Exception(
            'Failed to auto-layout scene: 400 - {"error":{"code":"OPERATION_FAILED","message":"The layout tool was unable to fit all of the selected models into the work area."}}'
        )
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4bl-lab"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["groups"][0]["status"] == "submitted"
    assert payload["groups"][1]["status"] == "submitted"

    jobs = list_print_jobs(settings)
    assert len(jobs) == 2
    assert {tuple(job.case_ids) for job in jobs} == {("CASE-A", "CASE-C"), ("CASE-B",)}
    assert all(job.printer_device_id == "form-4bl-lab" for job in jobs)

    smallest_row = get_upload_row_by_id(settings, row_ids[1])
    assert smallest_row is not None
    assert smallest_row.status == "Submitted"
    assert smallest_row.queue_section == "history"


def test_send_to_print_submits_single_validation_warning_after_saving_form(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "invalid-case.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-INVALID",
                preset="Tooth - With Supports",
                status="Ready",
                content_hash="hash-invalid",
                model_type="Tooth",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.validation_results = [{"valid": False, "errors": ["overlap"]}]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    row = response.json()[0]
    assert row["status"] == "Submitted"
    assert row["review_required"] is False
    assert row["review_reason"] is None
    expected_job_name = f"{datetime.now().strftime('%y%m%d')}_0001"
    expected_form_path = settings.output_dir / expected_job_name / f"{expected_job_name}.form"
    assert stub_client.saved_forms == [("scene-1", str(expected_form_path.resolve()))]
    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].validation_passed is False
    assert jobs[0].validation_errors == ["overlap"]


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
                model_type="Tooth",
                printer="printer_form4_001",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    assert stub_client.imported_models == [("scene-1", str(case_file), "tooth_v1")]
    assert stub_client.print_jobs == []
    jobs = list_print_jobs(settings)
    assert jobs[0].form_file_path == str((settings.output_dir / jobs[0].job_name / f"{jobs[0].job_name}.form").resolve())


def test_send_to_print_defaults_to_form4bl_when_no_printer_selected(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "ortho-1.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE901",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-901",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    assert stub_client.print_jobs == []
    jobs = list_print_jobs(settings)
    assert jobs[0].printer_type == "Form 4BL"
    assert jobs[0].form_file_path == str((settings.output_dir / jobs[0].job_name / f"{jobs[0].job_name}.form").resolve())


def test_send_to_print_holds_final_below_target_build_with_preform_preview_without_dispatch(tmp_path):
    settings = _build_holding_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "hold-1.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(case_file), 40.0, 30.0)
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-HOLD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-hold",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    row = response.json()[0]
    assert row["status"] == "Submitted"
    assert row["queue_section"] == "in_progress"
    assert row["handoff_stage"] == "Holding for More Cases"
    assert stub_client.created_scenes == [
        ("CASE-HOLD", datetime.now().strftime("%y%m%d") + "_0001")
    ]
    assert stub_client.print_jobs == []

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].status == "Holding for More Cases"
    assert jobs[0].form_file_path == str((settings.output_dir / jobs[0].job_name / f"{jobs[0].job_name}.form").resolve())
    assert jobs[0].printer_type == "Form 4BL"
    assert jobs[0].resin == "Precision Model V1"
    assert jobs[0].layer_height_microns == 100
    assert jobs[0].estimated_density == 1200.0 / 69188.0
    assert jobs[0].density_target == 0.40
    assert jobs[0].hold_reason == "below_density_target"
    assert jobs[0].manifest_json["estimated_density"] == 1200.0 / 69188.0
    assert jobs[0].screenshot_url == f"/api/print-queue/jobs/{jobs[0].id}/screenshot"

    screenshot_response = client.get(f"/api/print-queue/jobs/{jobs[0].id}/screenshot")

    assert screenshot_response.status_code == 200
    assert screenshot_response.headers["content-type"] == "image/png"
    assert screenshot_response.content == b"preform-screenshot-png"


def test_selected_device_send_to_print_holds_final_below_target_build(tmp_path):
    """Device dispatch path must respect density-based holding, same as non-device path."""
    settings = _build_holding_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "device-hold-1.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(case_file), 40.0, 30.0)
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-DEVICE-HOLD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-hold",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-lab", "name": "Lab Printer", "model": "Form 4BL", "status": "ready"}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": row_ids, "device_id": "form-4bl-lab"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["groups"][0]["status"] == "held"
    assert stub_client.created_scenes == [
        ("CASE-DEVICE-HOLD", datetime.now().strftime("%y%m%d") + "_0001")
    ]
    assert stub_client.print_jobs == []

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].status == "Holding for More Cases"
    assert jobs[0].form_file_path == str((settings.output_dir / jobs[0].job_name / f"{jobs[0].job_name}.form").resolve())
    assert jobs[0].hold_reason == "below_density_target"
    assert jobs[0].printer_device_id == "form-4bl-lab"
    assert jobs[0].estimated_density == 1200.0 / 69188.0
    assert jobs[0].density_target == 0.40


def test_release_held_job_dispatches_and_records_operator_release(tmp_path):
    settings = _build_holding_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "hold-release.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-RELEASE",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-release",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        hold_response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})
        held_job_id = list_print_jobs(settings)[0].id
        release_response = client.post(f"/api/print-queue/jobs/{held_job_id}/release-now")

    assert hold_response.status_code == 200
    assert release_response.status_code == 200
    assert stub_client.created_scenes == [
        ("CASE-RELEASE", datetime.now().strftime("%y%m%d") + "_0001"),
        ("CASE-RELEASE", datetime.now().strftime("%y%m%d") + "_0001")
    ]
    assert stub_client.print_jobs == []

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].status == "Queued"
    assert jobs[0].print_job_id is None
    assert jobs[0].form_file_path == str((settings.output_dir / jobs[0].job_name / f"{jobs[0].job_name}.form").resolve())
    assert jobs[0].screenshot_url == f"/api/print-queue/jobs/{jobs[0].id}/screenshot"
    assert jobs[0].release_reason == "operator_release"
    assert jobs[0].released_by_operator is True

    screenshot_response = client.get(f"/api/print-queue/jobs/{jobs[0].id}/screenshot")

    assert screenshot_response.status_code == 200
    assert screenshot_response.content == b"preform-screenshot-png"


def test_cutoff_poll_releases_held_job_created_in_current_process(tmp_path):
    settings = _build_holding_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "hold-cutoff.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-CUTOFF",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-cutoff",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        hold_response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})
        held_job_id = list_print_jobs(settings)[0].id
        with connect(settings) as connection:
            connection.execute(
                "UPDATE print_jobs SET hold_cutoff_at = ? WHERE id = ?",
                ("2000-01-01T00:00:00", held_job_id),
            )
            connection.commit()
        jobs_response = client.get("/api/print-queue/jobs")

    assert hold_response.status_code == 200
    assert jobs_response.status_code == 200
    assert stub_client.print_jobs == []

    jobs = list_print_jobs(settings)
    assert jobs[0].status == "Queued"
    assert jobs[0].print_job_id is None
    assert jobs[0].form_file_path == str((settings.output_dir / jobs[0].job_name / f"{jobs[0].job_name}.form").resolve())
    assert jobs[0].release_reason == "cutoff_release"
    assert jobs[0].released_by_operator is False


def test_new_compatible_rows_replan_with_existing_held_build(tmp_path):
    settings = _build_holding_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    held_file = tmp_path / "held.stl"
    filler_file = tmp_path / "filler.stl"
    for file_path in (held_file, filler_file):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(held_file), 40.0, 30.0)
    register_test_dims(str(filler_file), 700.0, 40.0)

    first_ids = _seed_rows(
        settings,
        [
            _row_payload(
                held_file,
                case_id="CASE-HELD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-held",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        first_response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": first_ids})

    assert first_response.status_code == 200
    assert list_print_jobs(settings)[0].status == "Holding for More Cases"
    assert stub_client.print_jobs == []

    second_ids = _seed_rows(
        settings,
        [
            _row_payload(
                filler_file,
                case_id="CASE-FILLER",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-filler",
                dimension_x_mm=700.0,
                dimension_y_mm=40.0,
            ),
        ],
    )

    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        second_response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": second_ids})

    assert second_response.status_code == 200
    assert stub_client.print_jobs == []
    assert stub_client.imported_models == [
        ("scene-1", str(held_file), "ortho_solid_v1"),
        ("scene-2", str(filler_file), "ortho_solid_v1"),
        ("scene-2", str(held_file), "ortho_solid_v1"),
    ]

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].status == "Queued"
    assert jobs[0].print_job_id is None
    assert jobs[0].form_file_path == str((settings.output_dir / jobs[0].job_name / f"{jobs[0].job_name}.form").resolve())
    assert set(jobs[0].case_ids) == {"CASE-HELD", "CASE-FILLER"}


def test_selected_device_new_compatible_rows_replan_with_existing_held_build(tmp_path):
    settings = _build_holding_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    held_file = tmp_path / "device-held.stl"
    filler_file = tmp_path / "device-filler.stl"
    for file_path in (held_file, filler_file):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(held_file), 40.0, 30.0)
    register_test_dims(str(filler_file), 700.0, 40.0)

    first_ids = _seed_rows(
        settings,
        [
            _row_payload(
                held_file,
                case_id="CASE-DEVICE-HELD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-held",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-lab", "name": "Lab Printer", "model": "Form 4BL", "status": "ready"}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        first_response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": first_ids, "device_id": "form-4bl-lab"},
        )

    assert first_response.status_code == 200
    assert list_print_jobs(settings)[0].status == "Holding for More Cases"
    assert stub_client.print_jobs == []

    second_ids = _seed_rows(
        settings,
        [
            _row_payload(
                filler_file,
                case_id="CASE-DEVICE-FILLER",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-filler",
                dimension_x_mm=700.0,
                dimension_y_mm=40.0,
            ),
        ],
    )

    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        second_response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": second_ids, "device_id": "form-4bl-lab"},
        )

    assert second_response.status_code == 200
    assert stub_client.imported_models == [
        ("scene-1", str(held_file), "ortho_solid_v1"),
        ("scene-2", str(filler_file), "ortho_solid_v1"),
        ("scene-2", str(held_file), "ortho_solid_v1"),
    ]

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].printer_device_id == "form-4bl-lab"
    assert jobs[0].printer_device_name == "Lab Printer"
    assert jobs[0].status == "Queued"
    assert jobs[0].hold_reason is None
    assert jobs[0].print_job_id == "print-1"
    assert jobs[0].form_file_path == str((settings.output_dir / jobs[0].job_name / f"{jobs[0].job_name}.form").resolve())
    assert set(jobs[0].case_ids) == {"CASE-DEVICE-HELD", "CASE-DEVICE-FILLER"}

    held_row = get_upload_row_by_id(settings, first_ids[0])
    filler_row = get_upload_row_by_id(settings, second_ids[0])
    assert held_row is not None
    assert filler_row is not None
    assert held_row.linked_print_job_id == jobs[0].id
    assert filler_row.linked_print_job_id == jobs[0].id
    assert held_row.queue_section == "history"
    assert filler_row.queue_section == "history"


def test_different_device_does_not_merge_existing_selected_device_hold(tmp_path):
    settings = _build_holding_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    held_file = tmp_path / "device-a-held.stl"
    device_b_file = tmp_path / "device-b-case.stl"
    for file_path in (held_file, device_b_file):
        file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    register_test_dims(str(held_file), 40.0, 30.0)
    register_test_dims(str(device_b_file), 40.0, 30.0)

    first_ids = _seed_rows(
        settings,
        [
            _row_payload(
                held_file,
                case_id="CASE-DEVICE-A-HELD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-a-held",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
        ],
    )
    second_ids = _seed_rows(
        settings,
        [
            _row_payload(
                device_b_file,
                case_id="CASE-DEVICE-B",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-device-b",
                dimension_x_mm=40.0,
                dimension_y_mm=30.0,
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-a", "name": "Printer A", "model": "Form 4BL", "status": "ready"},
        {"id": "form-4bl-b", "name": "Printer B", "model": "Form 4BL", "status": "ready"},
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        first_response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": first_ids, "device_id": "form-4bl-a"},
        )
        second_response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": second_ids, "device_id": "form-4bl-b"},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    jobs = list_print_jobs(settings)
    assert len(jobs) == 2
    assert {job.printer_device_id for job in jobs} == {"form-4bl-a", "form-4bl-b"}
    assert all(job.status == "Holding for More Cases" for job in jobs)


def test_busy_lane_does_not_delete_existing_held_job(tmp_path):
    from app.database import get_upload_row_by_id, try_acquire_build_lane_lock
    from app.services.build_planning import plan_build_manifests
    from app.services.print_queue_service import _build_lane_keys_from_manifests

    settings = replace(_build_settings(tmp_path), print_hold_density_target=0.95)
    app = create_app(settings)
    client = TestClient(app)

    held_file = tmp_path / "held.stl"
    held_file.write_text("solid held\nendsolid held\n", encoding="utf-8")
    held_ids = _seed_rows(
        settings,
        [
            _row_payload(
                held_file,
                case_id="CASE-ALREADY-HELD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-already-held",
                dimension_x_mm=20.0,
                dimension_y_mm=20.0,
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {
            "id": "form-4bl-lab",
            "name": "Lab Printer",
            "model": "Form 4BL",
            "status": "Ready",
            "is_virtual": True,
        }
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        first_response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": held_ids, "device_id": "form-4bl-lab"},
        )

    assert first_response.status_code == 200
    existing_job = list_print_jobs(settings)[0]
    assert existing_job.status == "Holding for More Cases"

    new_file = tmp_path / "new-compatible.stl"
    new_file.write_text("solid new\nendsolid new\n", encoding="utf-8")
    new_ids = _seed_rows(
        settings,
        [
            _row_payload(
                new_file,
                case_id="CASE-NEW-HELD",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-new-held",
                dimension_x_mm=20.0,
                dimension_y_mm=20.0,
            ),
        ],
    )
    new_rows = [get_upload_row_by_id(settings, new_ids[0])]
    lane_key = _build_lane_keys_from_manifests(
        plan_build_manifests(new_rows),
        device_id="form-4bl-lab",
    )[0]
    assert try_acquire_build_lane_lock(settings, lane_key, "external-prep", "send")

    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        second_response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": new_ids, "device_id": "form-4bl-lab"},
        )

    assert second_response.status_code == 200
    jobs = list_print_jobs(settings)
    assert {job.status for job in jobs} == {"Holding for More Cases"}
    assert {case_id for job in jobs for case_id in job.case_ids} == {
        "CASE-ALREADY-HELD",
        "CASE-NEW-HELD",
    }
    assert get_upload_row_by_id(settings, held_ids[0]).queue_section == "in_progress"
    assert get_upload_row_by_id(settings, new_ids[0]).queue_section == "in_progress"


def test_busy_lane_held_job_on_other_device_survives_send_to_print(tmp_path):
    from app.database import get_upload_row_by_id, try_acquire_build_lane_lock
    from app.services.build_planning import plan_build_manifests
    from app.services.print_queue_service import _build_lane_keys_from_manifests

    settings = replace(_build_settings(tmp_path), print_hold_density_target=0.95)
    app = create_app(settings)
    client = TestClient(app)

    busy_file = tmp_path / "busy-a.stl"
    other_file = tmp_path / "other-b.stl"
    busy_file.write_text("solid busy\nendsolid busy\n", encoding="utf-8")
    other_file.write_text("solid other\nendsolid other\n", encoding="utf-8")
    busy_ids = _seed_rows(
        settings,
        [
            _row_payload(
                busy_file,
                case_id="CASE-BUSY-A",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-busy-a",
                dimension_x_mm=20.0,
                dimension_y_mm=20.0,
            ),
        ],
    )
    other_ids = _seed_rows(
        settings,
        [
            _row_payload(
                other_file,
                case_id="CASE-OTHER-B",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-other-b",
                dimension_x_mm=20.0,
                dimension_y_mm=20.0,
            ),
        ],
    )

    row = get_upload_row_by_id(settings, busy_ids[0])
    lane_key = _build_lane_keys_from_manifests(
        plan_build_manifests([row]),
        device_id="form-4bl-a",
    )[0]
    assert try_acquire_build_lane_lock(settings, lane_key, "external-prep", "send")

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-a", "name": "Printer A", "model": "Form 4BL", "status": "Ready"},
        {"id": "form-4bl-b", "name": "Printer B", "model": "Form 4BL", "status": "Ready"},
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ), patch("app.services.print_queue_service.validate_stl_file", return_value=Mock(is_valid=True, message="OK")):
        first_response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": busy_ids, "device_id": "form-4bl-a"},
        )
        assert first_response.status_code == 200
        busy_job = list_print_jobs(settings)[0]
        assert busy_job.hold_reason == "busy_lane"

        second_response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": other_ids, "device_id": "form-4bl-b"},
        )

    assert second_response.status_code == 200
    jobs = list_print_jobs(settings)
    assert {job.printer_device_id for job in jobs} == {"form-4bl-a", "form-4bl-b"}
    assert any(job.id == busy_job.id and job.hold_reason == "busy_lane" for job in jobs)
    busy_row = get_upload_row_by_id(settings, busy_ids[0])
    assert busy_row.linked_print_job_id == busy_job.id


def test_overflow_pool_busy_lane_creates_single_held_job(tmp_path):
    """When the lane is busy, exactly one busy_lane held job covers the entire pool.

    Pre-refactor: pre-planned 2 manifests, each independently hits BuildLaneBusyError,
    creating 2 held jobs.
    Post-refactor: pack-one-at-a-time tries the first tray, hits busy lane, holds the
    pool as a single job, and stops.
    """
    from app.database import try_acquire_build_lane_lock
    from app.services.build_planning import plan_build_manifests
    from app.services.print_queue_service import _build_lane_keys_from_manifests

    settings = replace(_build_settings(tmp_path), print_hold_density_target=0.95)
    app = create_app(settings)
    client = TestClient(app)

    stl_a = tmp_path / "case_a.stl"
    stl_b = tmp_path / "case_b.stl"
    stl_a.write_text("solid a\nendsolid a\n", encoding="utf-8")
    stl_b.write_text("solid b\nendsolid b\n", encoding="utf-8")

    # Register large XY footprint so the two arches overflow 60% cap when combined
    register_test_dims(str(stl_a), 230.0, 180.0)
    register_test_dims(str(stl_b), 230.0, 180.0)

    # Two large full-arches that overflow the 60% density cap when combined
    all_ids = _seed_rows(
        settings,
        [
            _row_payload(stl_a, case_id="OVERFLOW-A",
                         preset="Ortho Solid - Flat, No Supports",
                         status="Ready", content_hash="hash-oa",
                         dimension_x_mm=230.0, dimension_y_mm=180.0),
            _row_payload(stl_b, case_id="OVERFLOW-B",
                         preset="Ortho Solid - Flat, No Supports",
                         status="Ready", content_hash="hash-ob",
                         dimension_x_mm=230.0, dimension_y_mm=180.0),
        ],
    )

    # Confirm test setup forces 2 manifests
    from app.database import _load_rows_by_ids
    with closing(connect(settings)) as conn:
        rows = _load_rows_by_ids(conn, all_ids)
    manifests = plan_build_manifests(rows, max_layout_density=0.60)
    assert len(manifests) == 2, f"Test setup must produce 2 manifests, got {len(manifests)}"
    lane_keys = _build_lane_keys_from_manifests(manifests, device_id="form-4bl-lab")
    assert len(lane_keys) == 1
    lane_key = next(iter(lane_keys))

    # Pre-acquire the lane lock to simulate busy
    try_acquire_build_lane_lock(settings, lane_key, "external-owner", "external")

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-lab", "name": "Lab Printer", "model": "Form 4BL",
         "status": "Ready", "is_virtual": True}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), \
         patch("app.services.preform_setup_service.get_preform_setup_status",
               return_value=_ready_setup_status(settings)), \
         patch("app.services.print_queue_service.validate_stl_file",
               return_value=Mock(is_valid=True, message="OK")):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": all_ids, "device_id": "form-4bl-lab"},
        )

    assert response.status_code == 200
    jobs = list_print_jobs(settings)
    held_jobs = [j for j in jobs if j.status == "Holding for More Cases"]
    assert len(held_jobs) == 1, (
        f"Expected exactly 1 held job, got {len(held_jobs)}. "
        f"Jobs: {[(j.id, j.status, j.hold_reason) for j in jobs]}"
    )
    held_job = held_jobs[0]
    assert held_job.hold_reason == "busy_lane"

    # All rows linked to that single job
    for row_id in all_ids:
        row = get_upload_row_by_id(settings, row_id)
        assert row is not None
        assert row.linked_print_job_id == held_job.id


def test_overflow_pool_sequentially_packs_and_holds_only_final_remainder(tmp_path):
    """A pool that produces multiple trays dispatches the full ones and holds only the final sparse one.

    Per architecture-doc §7, each iteration runs the same packing procedure: largest-first seed,
    fill descending while it fits the 60% cap, smallest-filler pass to top up. The held tray is
    the final remainder — what genuinely couldn't be absorbed by any preceding iteration.
    """
    settings = _build_holding_settings(tmp_path)  # density_target=0.40, cutoff=23:59
    app = create_app(settings)
    client = TestClient(app)

    # Three cases. Two large (~29.5% effective each), one tiny (~3%).
    # Iteration 1 packs LARGE-A + LARGE-B (~59% density, >= 40% target) -> Queued.
    # If TINY fits the smallest-filler pass of iteration 1, it joins; otherwise iteration 2 holds it.
    # Test relies on dimensions chosen so smallest-filler does NOT fit TINY into iteration 1
    # (sufficient when the two large arches consume most of the 60% cap budget).
    stls = [tmp_path / f"case_{i}.stl" for i in range(3)]
    for s in stls:
        s.write_text(f"solid {s.name}\nendsolid {s.name}\n", encoding="utf-8")

    register_test_dims(str(stls[0]), 220.0, 160.0)
    register_test_dims(str(stls[1]), 220.0, 160.0)
    register_test_dims(str(stls[2]), 50.0, 40.0, "Tooth")

    all_ids = _seed_rows(
        settings,
        [
            _row_payload(stls[0], case_id="LARGE-A",
                         preset="Ortho Solid - Flat, No Supports",
                         status="Ready", content_hash="h-la",
                         dimension_x_mm=220.0, dimension_y_mm=160.0),
            _row_payload(stls[1], case_id="LARGE-B",
                         preset="Ortho Solid - Flat, No Supports",
                         status="Ready", content_hash="h-lb",
                         dimension_x_mm=220.0, dimension_y_mm=160.0),
            _row_payload(stls[2], case_id="TINY",
                         preset="Tooth - With Supports",
                         status="Ready", content_hash="h-t",
                         dimension_x_mm=50.0, dimension_y_mm=40.0),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.devices = [
        {"id": "form-4bl-lab", "name": "Lab Printer", "model": "Form 4BL",
         "status": "Ready", "is_virtual": True}
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), \
         patch("app.services.preform_setup_service.get_preform_setup_status",
               return_value=_ready_setup_status(settings)), \
         patch("app.services.print_queue_service.validate_stl_file",
               return_value=Mock(is_valid=True, message="OK")):
        response = client.post(
            "/api/uploads/rows/send-to-print",
            json={"row_ids": all_ids, "device_id": "form-4bl-lab"},
        )

    assert response.status_code == 200
    jobs = list_print_jobs(settings)
    queued = [j for j in jobs if j.status == "Queued"]
    held = [j for j in jobs if j.status == "Holding for More Cases"]

    # Exactly one Queued (the full tray) and at most one Held (the final remainder)
    assert len(queued) >= 1, f"Expected at least 1 Queued, got {len(queued)}"
    assert len(held) <= 1, f"Expected at most 1 Held, got {len(held)}"

    # If TINY ended up held, hold_reason must be below_density_target
    if held:
        assert held[0].hold_reason == "below_density_target"
        assert set(held[0].case_ids) == {"TINY"}

    # The Queued tray must contain both large cases together
    queued_cases = set(queued[0].case_ids)
    assert "LARGE-A" in queued_cases
    assert "LARGE-B" in queued_cases


def test_send_to_print_marks_rows_with_history_job_link_metadata(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "ortho-history.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-HISTORY",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-history",
            ),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    row = response.json()[0]
    assert row["status"] == "Submitted"
    assert row["queue_section"] == "history"
    assert row["handoff_stage"] == "Queued"
    assert row["linked_job_name"] == f"{datetime.now().strftime('%y%m%d')}_0001"


def test_send_to_print_does_not_require_volume_before_handoff(tmp_path, monkeypatch):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "volume-pending.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE-VOLUME",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-volume-pending",
                volume_ml=None,
            ),
        ],
    )

    from app.services import volume_enrichment

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Send-to-print should not compute exact STL volume")

    monkeypatch.setattr(volume_enrichment, "get_stl_volume_ml", fail_if_called)
    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    row = response.json()[0]
    assert row["status"] == "Submitted"
    assert row["queue_section"] == "history"
    assert row["handoff_stage"] == "Queued"
    assert stub_client.created_scenes == [
        ("CASE-VOLUME", f"{datetime.now().strftime('%y%m%d')}_0001")
    ]
    updated = get_upload_row_by_id(settings, row_ids[0])
    assert updated is not None
    assert updated.volume_ml is None


def test_send_to_print_returns_502_when_preform_unavailable(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "case-1.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
    row_ids = _seed_rows(
        settings,
        [
            _row_payload(
                case_file,
                case_id="CASE001",
                preset="Ortho Solid - Flat, No Supports",
                status="Ready",
                content_hash="hash-1",
            ),
        ],
    )

    mock_client = Mock()
    mock_client.create_scene.side_effect = Exception("Connection refused")
    mock_client.close.return_value = None

    with patch("app.services.preform_client.PreFormClient", return_value=mock_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 502
    assert "Connection refused" in response.json()["detail"]
    assert get_upload_row_by_id(settings, row_ids[0]).status == "Ready"
    assert list_print_jobs(settings) == []
