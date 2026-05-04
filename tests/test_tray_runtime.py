from __future__ import annotations

from pathlib import Path
import socket

from desktop.tray_runtime import (
    FormFlowServerManager,
    FormFlowTrayRuntime,
    RuntimePaths,
    TrayStatus,
    build_status_message,
    configure_runtime_environment,
    create_diagnostic_logger,
    create_tray_icon,
    decide_tray_status,
    is_port_open,
    tray_menu_labels,
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


def test_tray_icon_uses_expected_center_pixel_colors():
    expected = {
        TrayStatus.READY: (0, 150, 0),
        TrayStatus.CHECKING: (220, 170, 0),
        TrayStatus.ERROR: (220, 0, 0),
    }

    for status, rgb in expected.items():
        image = create_tray_icon(status)
        assert image.getpixel((32, 32))[:3] == rgb


def test_is_port_open_reports_listening_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
    try:
        assert is_port_open("127.0.0.1", port) is True
    finally:
        sock.close()


def test_is_port_open_reports_closed_port():
    assert is_port_open("127.0.0.1", 9) is False


def test_server_manager_stop_sets_should_exit_and_joins(monkeypatch):
    events: list[str] = []

    class FakeServer:
        should_exit = False

        def run(self):
            events.append("run")

    manager = FormFlowServerManager(host="127.0.0.1", port=8090, app_factory=lambda: object())
    manager.server = FakeServer()

    class FakeThread:
        def __init__(self):
            self.join_timeout = None

        def is_alive(self):
            return False

        def join(self, timeout):
            self.join_timeout = timeout
            events.append(f"join:{timeout}")

    thread = FakeThread()
    manager.thread = thread

    assert manager.stop(join_timeout_s=1.5) is True
    assert manager.server.should_exit is True
    assert "join:1.5" in events


def test_server_manager_disables_uvicorn_default_logging_for_windowed_exe(monkeypatch):
    config_kwargs: dict[str, object] = {}

    class FakeConfig:
        def __init__(self, app, **kwargs):
            config_kwargs.update(kwargs)

    class FakeServer:
        def __init__(self, config):
            self.config = config

        def run(self):
            return None

    class FakeThread:
        def __init__(self, *, target, name, daemon):
            self.target = target

        def is_alive(self):
            return False

        def start(self):
            return None

    monkeypatch.setattr("desktop.tray_runtime.uvicorn.Config", FakeConfig)
    monkeypatch.setattr("desktop.tray_runtime.uvicorn.Server", FakeServer)
    monkeypatch.setattr("desktop.tray_runtime.threading.Thread", FakeThread)

    manager = FormFlowServerManager(host="127.0.0.1", port=8090, app_factory=lambda: object())
    manager.start()

    assert config_kwargs["log_config"] is None


def test_tray_menu_labels_match_operator_actions():
    assert tray_menu_labels() == [
        "Open FormFlow",
        "Server Status",
        "Re-check PreFormServer",
        "Restart FormFlow",
        "View Logs",
        "Quit",
    ]


def test_refresh_status_turns_ready_payload_green(tmp_path):
    paths = RuntimePaths.from_root(tmp_path)
    runtime = FormFlowTrayRuntime(
        paths=paths,
        host="127.0.0.1",
        port=8090,
        logger=lambda message: None,
        server_manager=None,
    )
    runtime.fetch_health = lambda: True
    runtime.fetch_preform_status = lambda: {
        "readiness": "ready",
        "detected_version": "3.58.1.627",
    }

    runtime.refresh_status(checking=False)

    assert runtime.status == TrayStatus.READY
    assert runtime.preform_payload["readiness"] == "ready"
