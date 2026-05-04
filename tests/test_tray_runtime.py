from __future__ import annotations

from pathlib import Path

from desktop.tray_runtime import (
    RuntimePaths,
    TrayStatus,
    build_status_message,
    configure_runtime_environment,
    create_diagnostic_logger,
    decide_tray_status,
)


def test_status_is_yellow_while_starting():
    status = decide_tray_status(formflow_healthy=False, preform_payload=None, checking=True)

    assert status == TrayStatus.CHECKING


def test_status_is_green_when_formflow_and_preform_are_ready():
    status = decide_tray_status(
        formflow_healthy=True,
        preform_payload={"readiness": "ready", "detected_version": "3.58.1.627"},
        checking=False,
    )

    assert status == TrayStatus.READY


def test_status_is_red_when_preform_is_not_installed():
    status = decide_tray_status(
        formflow_healthy=True,
        preform_payload={"readiness": "not_installed"},
        checking=False,
    )

    assert status == TrayStatus.ERROR


def test_status_is_red_when_formflow_health_fails():
    status = decide_tray_status(formflow_healthy=False, preform_payload=None, checking=False)

    assert status == TrayStatus.ERROR


def test_status_message_includes_preform_readiness_and_version():
    message = build_status_message(
        url="http://127.0.0.1:8090",
        status=TrayStatus.READY,
        preform_payload={"readiness": "ready", "detected_version": "3.58.1.627"},
        logs_dir=Path("C:/logs"),
    )

    assert "http://127.0.0.1:8090" in message
    assert "ready" in message
    assert "3.58.1.627" in message
    assert "C:/logs" in message


def test_configure_runtime_environment_sets_packaged_defaults(tmp_path, monkeypatch):
    runtime_root = tmp_path / "dist"
    paths = RuntimePaths.from_root(runtime_root)

    monkeypatch.delenv("FORMFLOW_WEB_DATA_DIR", raising=False)
    monkeypatch.delenv("FORMFLOW_WEB_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("FORMFLOW_WEB_DATABASE_PATH", raising=False)
    monkeypatch.delenv("FORMFLOW_WEB_HOST", raising=False)
    monkeypatch.delenv("FORMFLOW_WEB_PORT", raising=False)

    host, port = configure_runtime_environment(paths)

    assert host == "127.0.0.1"
    assert port == 8090
    assert paths.data_dir.exists()
    assert paths.output_dir.exists()
    assert paths.logs_dir.exists()
    assert paths.uploads_dir.exists()


def test_create_diagnostic_logger_writes_before_app_imports(tmp_path):
    paths = RuntimePaths.from_root(tmp_path)
    logger = create_diagnostic_logger(paths)

    logger("startup marker")

    log_text = (paths.logs_dir / "formflow_tray_diagnostic.log").read_text(encoding="utf-8")
    assert "startup marker" in log_text
