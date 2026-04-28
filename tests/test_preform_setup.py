"""Phase 1: PreFormServer setup wizard tests (TDD)."""

from __future__ import annotations

import sys
import zipfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import build_settings
from app.database import init_db, persist_upload_session
from app.main import create_app


def _build_settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    return build_settings(data_dir=data_dir, database_path=data_dir / "andent_web.db")


def _build_client(tmp_path: Path) -> tuple[TestClient, object]:
    settings = _build_settings(tmp_path)
    init_db(settings)
    app = create_app(settings)
    return TestClient(app), settings


def _row_payload(file_path: Path, *, status: str = "Ready") -> dict:
    return {
        "file_name": file_path.name,
        "stored_path": str(file_path),
        "content_hash": f"hash-{file_path.name}",
        "thumbnail_svg": None,
        "case_id": "CASE001",
        "model_type": "Ortho - Solid",
        "preset": "Ortho Solid - Flat, No Supports",
        "confidence": "high",
        "status": status,
        "dimension_x_mm": 40.0,
        "dimension_y_mm": 30.0,
        "dimension_z_mm": 10.0,
        "volume_ml": None,
        "structure": None,
        "structure_confidence": None,
        "structure_reason": None,
        "structure_metrics_json": None,
        "structure_locked": False,
        "review_required": status != "Ready",
        "review_reason": None,
        "printer": None,
        "person": None,
    }


def _seed_ready_row(settings, tmp_path: Path) -> int:
    stl_path = tmp_path / "case-1.stl"
    stl_path.write_text("solid test\nendsolid test\n", encoding="utf-8")
    session_id = f"session-{datetime.now(timezone.utc).timestamp():.0f}"
    rows = persist_upload_session(settings, session_id, [_row_payload(stl_path)])
    assert rows[0].row_id is not None
    return rows[0].row_id


def _build_preform_zip(tmp_path: Path, *, version_text: str = "3.57.2.624") -> Path:
    archive_path = tmp_path / "PreFormServer_3.57.2.624.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("PreFormServer/PreFormServer.exe", "fake exe payload")
        archive.writestr("PreFormServer/version.txt", version_text)
        archive.writestr("PreFormServer/config/default.json", "{}")
    return archive_path


def _build_preform_zip_without_version_file(tmp_path: Path) -> Path:
    archive_path = tmp_path / "PreFormServer_3.58.1.627.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("PreFormServer/PreFormServer.exe", "fake exe payload")
        archive.writestr("PreFormServer/config/default.json", "{}")
    return archive_path


def _build_invalid_zip(tmp_path: Path) -> Path:
    archive_path = tmp_path / "not-preform.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("README.txt", "missing exe")
    return archive_path


def test_setup_status_defaults_to_not_installed(tmp_path, monkeypatch):
    from app.services.preform_setup_service import PreFormSetupService, get_preform_setup_status

    _unhealthy = lambda self: {"healthy": False, "version": None, "code": "connection_error", "message": "no server"}
    monkeypatch.setattr(PreFormSetupService, "_probe_server", _unhealthy)

    settings = _build_settings(tmp_path)
    init_db(settings)

    status = get_preform_setup_status(settings)

    assert status.readiness == "not_installed"
    assert status.install_path == str(settings.preform_managed_dir)
    assert status.managed_executable_path == str(settings.preform_managed_executable)
    assert status.detected_version is None
    assert status.last_error_code is None


def test_default_supported_version_accepts_working_local_preform_build(tmp_path):
    from app.services.preform_setup_service import PreFormSetupService

    settings = _build_settings(tmp_path)
    init_db(settings)
    manager = PreFormSetupService(settings)

    assert manager._version_is_supported("3.49.0.532") is True


def test_default_preform_url_uses_loopback_ip_not_localhost(tmp_path, monkeypatch):
    monkeypatch.delenv("PREFORM_SERVER_URL", raising=False)

    settings = _build_settings(tmp_path)

    assert settings.preform_server_url == "http://127.0.0.1:44388"


def test_launch_process_includes_managed_runtime_paths(tmp_path, monkeypatch):
    from app.services.preform_setup_service import PreFormSetupService

    settings = _build_settings(tmp_path)
    init_db(settings)
    settings.preform_managed_dir.mkdir(parents=True, exist_ok=True)
    settings.preform_managed_executable.write_text("fake exe", encoding="utf-8")
    (settings.preform_managed_dir / "hoops").mkdir(parents=True, exist_ok=True)

    captured: dict[str, object] = {}

    class _FakeProcess:
        pid = 7777

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeProcess()

    monkeypatch.setattr("app.services.preform_setup_service.subprocess.Popen", fake_popen)

    manager = PreFormSetupService(settings)
    pid = manager._launch_process(settings.preform_managed_executable)

    assert pid == 7777
    assert captured["kwargs"]["cwd"] == str(settings.preform_managed_dir)
    env_path = captured["kwargs"]["env"]["PATH"]
    assert str(settings.preform_managed_dir) in env_path
    assert str(settings.preform_managed_dir / "hoops") in env_path


def test_start_reuses_existing_ready_preform_api_without_launching_duplicate(tmp_path):
    from app.services.preform_setup_service import PreFormSetupService

    settings = _build_settings(tmp_path)
    init_db(settings)
    settings.preform_managed_dir.mkdir(parents=True, exist_ok=True)
    settings.preform_managed_executable.write_text("fake exe", encoding="utf-8")

    manager = PreFormSetupService(settings)
    manager._probe_server = lambda: {
        "healthy": True,
        "version": "3.58.1.627",
        "code": None,
        "message": None,
    }

    def fail_launch(executable_path: Path) -> int:
        raise AssertionError(f"unexpected duplicate launch: {executable_path}")

    manager._launch_process = fail_launch

    status = manager.start()

    assert status.readiness == "ready"
    assert status.detected_version == "3.58.1.627"
    assert status.is_running is True


def test_probe_server_does_not_treat_missing_health_endpoint_as_ready(tmp_path, monkeypatch):
    import requests
    from app.services.preform_setup_service import PreFormSetupService

    settings = _build_settings(tmp_path)
    init_db(settings)
    manager = PreFormSetupService(settings)

    class _FakeResponse:
        def __init__(self, status_code: int, body: str):
            self.status_code = status_code
            self.text = body
            self.ok = 200 <= status_code < 300

        def json(self):
            raise ValueError("not json")

    class _FakeSession:
        def get(self, url: str, timeout: float):
            if url.endswith("/health") or url.endswith("/health/ready"):
                return _FakeResponse(404, "not found")
            raise requests.ConnectionError("connection refused")

        def close(self):
            pass

    monkeypatch.setattr("app.services.preform_setup_service.requests.Session", _FakeSession)

    probe = manager._probe_server()

    assert probe["healthy"] is False
    assert probe["code"] == "health_check_failed"


def test_install_from_zip_extracts_managed_copy_and_marks_ready(tmp_path):
    from app.services.preform_setup_service import PreFormSetupService

    settings = _build_settings(tmp_path)
    settings = replace(settings, preform_min_zip_size_bytes=1)
    init_db(settings)
    archive_path = _build_preform_zip(tmp_path)
    app = create_app(settings)

    def fake_launch(executable_path: Path) -> int:
        assert executable_path == settings.preform_managed_executable
        return 4242

    def fake_probe():
        return {
            "healthy": True,
            "version": "3.57.2.624",
            "code": None,
            "message": None,
        }

    manager = PreFormSetupService(app.state.settings)
    manager._launch_process = fake_launch
    manager._probe_server = fake_probe

    status = manager.install_from_zip(archive_path)

    assert status.readiness == "ready"
    assert status.detected_version == "3.57.2.624"
    assert settings.preform_managed_executable.exists()


def test_install_from_zip_records_filename_version_when_package_has_no_version_file(tmp_path):
    from app.services.preform_setup_service import PreFormSetupService

    settings = _build_settings(tmp_path)
    settings = replace(settings, preform_min_zip_size_bytes=1)
    init_db(settings)
    archive_path = _build_preform_zip_without_version_file(tmp_path)
    manager = PreFormSetupService(settings)

    manager._launch_process = lambda executable_path: 4242
    manager._probe_server = lambda: {
        "healthy": True,
        "version": manager._read_managed_version() or "0.0.0",
        "code": None,
        "message": None,
    }

    status = manager.install_from_zip(archive_path)

    assert status.readiness == "ready"
    assert status.detected_version == "3.58.1.627"
    assert (settings.preform_managed_dir / "version.txt").read_text(encoding="utf-8") == "3.58.1.627"


def test_install_from_zip_rejects_archive_without_preformserver_exe(tmp_path):
    from app.services.preform_setup_service import PreFormSetupError, PreFormSetupService

    settings = _build_settings(tmp_path)
    settings = replace(settings, preform_min_zip_size_bytes=1)
    init_db(settings)
    archive_path = _build_invalid_zip(tmp_path)

    manager = PreFormSetupService(settings)

    with pytest.raises(PreFormSetupError) as exc_info:
        manager.install_from_zip(archive_path)

    assert exc_info.value.code == "bad_zip"


def test_status_route_returns_not_installed_for_fresh_app(tmp_path, monkeypatch):
    from app.services.preform_setup_service import PreFormSetupService

    _unhealthy = lambda self: {"healthy": False, "version": None, "code": "connection_error", "message": "no server"}
    monkeypatch.setattr(PreFormSetupService, "_probe_server", _unhealthy)

    client, _ = _build_client(tmp_path)

    response = client.get("/api/preform-setup/status")

    assert response.status_code == 200
    assert response.json()["readiness"] == "not_installed"


def test_dispatch_mode_route_defaults_to_current_runtime_setting(tmp_path):
    client, settings = _build_client(tmp_path)

    response = client.get("/api/preform-setup/dispatch-mode")

    assert response.status_code == 200
    assert response.json() == {
        "mode": settings.print_dispatch_mode,
        "default_mode": settings.print_dispatch_mode,
        "allowed_modes": ["save_form", "virtual"],
    }


def test_dispatch_mode_route_updates_current_server_process_only(tmp_path):
    client, settings = _build_client(tmp_path)

    response = client.patch(
        "/api/preform-setup/dispatch-mode",
        json={"mode": "virtual"},
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "virtual"
    assert response.json()["default_mode"] == "save_form"
    assert client.app.state.settings.print_dispatch_mode == "virtual"
    assert settings.print_dispatch_mode == "save_form"


def test_dispatch_mode_route_rejects_real_printer_mode_from_ui(tmp_path):
    client, _settings = _build_client(tmp_path)

    response = client.patch(
        "/api/preform-setup/dispatch-mode",
        json={"mode": "real"},
    )

    assert response.status_code == 422


def test_explicit_preform_url_can_be_ready_without_managed_install(tmp_path, monkeypatch):
    from app.services.preform_setup_service import PreFormSetupService

    settings = _build_settings(tmp_path)
    init_db(settings)

    manager = PreFormSetupService(settings)
    monkeypatch.setattr(
        manager,
        "_probe_server",
        lambda: {
            "healthy": True,
            "version": "3.57.2.624",
            "code": None,
            "message": None,
        },
    )

    status = manager.recheck()

    assert status.readiness == "ready"
    assert status.detected_version == "3.57.2.624"
    assert status.is_running is True


def test_send_to_print_returns_409_when_preform_not_ready(tmp_path, monkeypatch):
    from app.services.preform_setup_service import PreFormSetupService

    _unhealthy = lambda self: {"healthy": False, "version": None, "code": "connection_error", "message": "no server"}
    monkeypatch.setattr(PreFormSetupService, "_probe_server", _unhealthy)

    client, settings = _build_client(tmp_path)
    row_id = _seed_ready_row(settings, tmp_path)

    response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": [row_id]})

    assert response.status_code == 409
    assert "PreFormServer setup is required" in response.json()["detail"]


def test_setup_center_static_ui_does_not_display_sensitive_install_path():
    index_html = Path("app/static/index.html").read_text(encoding="utf-8")
    app_js = Path("app/static/app.js").read_text(encoding="utf-8")

    assert "Install Path" not in index_html
    assert "preform-install-path" not in index_html
    assert "status.install_path" not in app_js
