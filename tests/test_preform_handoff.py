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
from app.database import connect, get_upload_row_by_id, init_db, list_print_jobs, persist_upload_session
from app.main import create_app
from app.schemas import PreFormSetupStatus


class StubPreFormClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.created_scenes: list[tuple[str, str]] = []
        self.imported_models: list[tuple[str, str, str | None]] = []
        self.layout_calls: list[str] = []
        self.validation_results: list[dict[str, object]] = []
        self.saved_forms: list[tuple[str, str]] = []
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
        return {"status": "ok"}

    def validate_scene(self, scene_id: str):
        if self.validation_results:
            return self.validation_results.pop(0)
        return {"valid": True, "errors": []}

    def save_form(self, scene_id: str, output_path: Path):
        self.saved_forms.append((scene_id, str(Path(output_path).resolve())))
        return {"status": "ok"}

    def list_devices(self):
        self.device_list_calls += 1
        return self.devices

    def send_to_printer(self, scene_id: str, device_id: str, job_name: str | None = None):
        self.print_jobs.append((scene_id, device_id, job_name))
        return {"print_id": f"print-{len(self.print_jobs)}"}

    def close(self):
        self.closed = True


def _build_settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    return replace(
        build_settings(data_dir=data_dir, database_path=data_dir / "andent_web.db"),
        print_hold_density_target=0.0,
    )


def _build_holding_settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    return replace(
        build_settings(data_dir=data_dir, database_path=data_dir / "andent_web.db"),
        print_hold_density_target=0.40,
        print_hold_cutoff_local_time="23:59",
    )


def _build_virtual_settings(tmp_path: Path):
    return replace(_build_settings(tmp_path), print_dispatch_mode="virtual")


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
    assert len(stub_client.layout_calls) == 1
    assert stub_client.print_jobs == []

    submitted_rows = {row["file_name"]: row["status"] for row in response.json()}
    assert submitted_rows["case-1.stl"] == "Submitted"
    assert submitted_rows["case-2.stl"] == "Submitted"
    assert submitted_rows["case-3.stl"] == "Submitted"
    assert submitted_rows["case-4.stl"] == "Check"

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    expected_form_path = case_files[0].parent / f"{jobs[0].job_name}.form"
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
    assert jobs[0].form_file_path == str((case_file.parent / f"{jobs[0].job_name}.form").resolve())
    assert response.json()[0]["status"] == "Submitted"


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
    monkeypatch.setenv("ANDENT_WEB_PRINT_DISPATCH_MODE", "unexpected")

    try:
        build_settings(data_dir=tmp_path / "data", database_path=tmp_path / "data" / "andent_web.db")
    except ValueError as exc:
        assert "ANDENT_WEB_PRINT_DISPATCH_MODE" in str(exc)
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

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].preset_names == [
        "Ortho Solid - Flat, No Supports",
        "Tooth - With Supports",
    ]
    assert jobs[0].compatibility_key == "form-4bl|precision-model-v1|100"
    assert jobs[0].manifest_json is not None
    assert jobs[0].manifest_json["case_ids"] == ["CASE-A", "CASE-B"]
    expected_form_path = case_a.parent / f"{jobs[0].job_name}.form"
    assert stub_client.saved_forms == [("scene-1", str(expected_form_path.resolve()))]
    assert jobs[0].form_file_path == str(expected_form_path.resolve())


def test_send_to_print_rolls_back_last_case_when_validation_fails_after_saving_form(tmp_path):
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
    stub_client.validation_results = [
        {"valid": False, "errors": ["overlap"]},
        {"valid": True, "errors": []},
    ]
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client), patch(
        "app.services.preform_setup_service.get_preform_setup_status",
        return_value=_ready_setup_status(settings),
    ):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    row_statuses = {row["file_name"]: row["status"] for row in response.json()}
    assert row_statuses["case-a.stl"] == "Submitted"
    assert row_statuses["case-b.stl"] == "Ready"
    assert row_statuses["case-c.stl"] == "Submitted"
    assert len(stub_client.created_scenes) == 2
    assert stub_client.imported_models == [
        ("scene-1", str(case_files[0]), "tooth_v1"),
        ("scene-1", str(case_files[2]), "ortho_solid_v1"),
        ("scene-1", str(case_files[1]), "ortho_solid_v1"),
        ("scene-2", str(case_files[0]), "tooth_v1"),
        ("scene-2", str(case_files[2]), "ortho_solid_v1"),
    ]
    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    expected_form_path = case_files[0].parent / f"{jobs[0].job_name}.form"
    assert stub_client.saved_forms == [
        ("scene-1", str(expected_form_path.resolve())),
        ("scene-2", str(expected_form_path.resolve())),
    ]
    assert jobs[0].validation_passed is True
    assert jobs[0].validation_errors == []
    assert jobs[0].case_ids == ["CASE-TOOTH", "CASE-LATE"]


def test_send_to_print_routes_single_invalid_case_to_manual_review_after_saving_form(tmp_path):
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
    assert row["status"] == "Needs Review"
    assert row["review_required"] is True
    assert row["review_reason"] == "PreForm validation requires manual review: overlap"
    expected_form_path = case_file.parent / f"{datetime.now().strftime('%y%m%d')}-001.form"
    assert stub_client.saved_forms == [("scene-1", str(expected_form_path.resolve()))]
    assert list_print_jobs(settings) == []


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
    assert jobs[0].form_file_path == str((case_file.parent / f"{jobs[0].job_name}.form").resolve())


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
    assert jobs[0].form_file_path == str((case_file.parent / f"{jobs[0].job_name}.form").resolve())


def test_send_to_print_holds_final_below_target_build_without_preform_dispatch(tmp_path):
    settings = _build_holding_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_file = tmp_path / "hold-1.stl"
    case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
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
    assert stub_client.created_scenes == []
    assert stub_client.print_jobs == []

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].status == "Holding for More Cases"
    assert jobs[0].printer_type == "Form 4BL"
    assert jobs[0].resin == "Precision Model V1"
    assert jobs[0].layer_height_microns == 100
    assert jobs[0].estimated_density == 1200.0 / 69188.0
    assert jobs[0].density_target == 0.40
    assert jobs[0].hold_reason == "below_density_target"
    assert jobs[0].manifest_json["estimated_density"] == 1200.0 / 69188.0


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
    assert stub_client.created_scenes == [("CASE-RELEASE", datetime.now().strftime("%y%m%d") + "-001")]
    assert stub_client.print_jobs == []

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].status == "Queued"
    assert jobs[0].print_job_id is None
    assert jobs[0].form_file_path == str((case_file.parent / f"{jobs[0].job_name}.form").resolve())
    assert jobs[0].release_reason == "operator_release"
    assert jobs[0].released_by_operator is True


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
    assert jobs[0].form_file_path == str((case_file.parent / f"{jobs[0].job_name}.form").resolve())
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
        ("scene-1", str(filler_file), "ortho_solid_v1"),
        ("scene-1", str(held_file), "ortho_solid_v1"),
    ]

    jobs = list_print_jobs(settings)
    assert len(jobs) == 1
    assert jobs[0].status == "Queued"
    assert jobs[0].print_job_id is None
    assert jobs[0].form_file_path == str((filler_file.parent / f"{jobs[0].job_name}.form").resolve())
    assert set(jobs[0].case_ids) == {"CASE-HELD", "CASE-FILLER"}


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
    assert row["linked_job_name"] == f"{datetime.now().strftime('%y%m%d')}-001"


def test_send_to_print_completes_missing_volume_before_handoff(tmp_path, monkeypatch):
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

    monkeypatch.setattr(volume_enrichment, "get_stl_volume_ml", lambda path: 2.75)
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
        ("CASE-VOLUME", f"{datetime.now().strftime('%y%m%d')}-001")
    ]
    updated = get_upload_row_by_id(settings, row_ids[0])
    assert updated is not None
    assert updated.volume_ml == 2.75


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
