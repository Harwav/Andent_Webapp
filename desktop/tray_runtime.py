from __future__ import annotations

import os
import json
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import uvicorn
from PIL import Image, ImageDraw


class TrayStatus(str, Enum):
    CHECKING = "checking"
    READY = "ready"
    ERROR = "error"


@dataclass(frozen=True)
class RuntimePaths:
    runtime_root: Path
    data_dir: Path
    uploads_dir: Path
    output_dir: Path
    logs_dir: Path
    database_path: Path

    @classmethod
    def from_root(cls, runtime_root: Path) -> "RuntimePaths":
        data_dir = Path(os.environ.get("FORMFLOW_WEB_DATA_DIR", runtime_root / "data"))
        output_dir = Path(os.environ.get("FORMFLOW_WEB_OUTPUT_DIR", runtime_root / "output"))
        return cls(
            runtime_root=runtime_root,
            data_dir=data_dir,
            uploads_dir=data_dir / "uploads",
            output_dir=output_dir,
            logs_dir=runtime_root / "logs",
            database_path=Path(
                os.environ.get("FORMFLOW_WEB_DATABASE_PATH", data_dir / "formflow.db")
            ),
        )


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def configure_runtime_environment(paths: RuntimePaths) -> tuple[str, int]:
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.uploads_dir.mkdir(parents=True, exist_ok=True)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("FORMFLOW_WEB_HOST", "127.0.0.1")
    os.environ.setdefault("FORMFLOW_WEB_PORT", "8090")
    os.environ.setdefault("FORMFLOW_WEB_DATA_DIR", str(paths.data_dir))
    os.environ.setdefault("FORMFLOW_WEB_OUTPUT_DIR", str(paths.output_dir))
    os.environ.setdefault("FORMFLOW_WEB_DATABASE_PATH", str(paths.database_path))
    return os.environ["FORMFLOW_WEB_HOST"], int(os.environ["FORMFLOW_WEB_PORT"])


def create_diagnostic_logger(paths: RuntimePaths) -> Callable[[str], None]:
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = paths.logs_dir / "formflow_tray_diagnostic.log"

    def log(message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")

    return log


def decide_tray_status(
    *,
    formflow_healthy: bool,
    preform_payload: dict[str, Any] | None,
    checking: bool,
) -> TrayStatus:
    if checking:
        return TrayStatus.CHECKING
    if not formflow_healthy:
        return TrayStatus.ERROR
    if preform_payload and preform_payload.get("readiness") == "ready":
        return TrayStatus.READY
    return TrayStatus.ERROR


def build_status_message(
    *,
    url: str,
    status: TrayStatus,
    preform_payload: dict[str, Any] | None,
    logs_dir: Path,
) -> str:
    readiness = (preform_payload or {}).get("readiness") or "unknown"
    version = (preform_payload or {}).get("detected_version") or "-"
    return (
        f"FormFlow status: {status.value}\n\n"
        f"URL: {url}\n"
        f"PreFormServer readiness: {readiness}\n"
        f"PreFormServer version: {version}\n"
        f"Logs: {logs_dir.as_posix()}"
    )


def create_tray_icon(status: TrayStatus) -> Image.Image:
    colors = {
        TrayStatus.READY: (0, 150, 0, 255),
        TrayStatus.CHECKING: (220, 170, 0, 255),
        TrayStatus.ERROR: (220, 0, 0, 255),
    }
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse([8, 8, 56, 56], fill=colors[status])
    return image


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


class FormFlowServerManager:
    def __init__(self, *, host: str, port: int, app_factory: Callable[[], Any]):
        self.host = host
        self.port = port
        self.app_factory = app_factory
        self.server: uvicorn.Server | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        config = uvicorn.Config(
            self.app_factory(),
            host=self.host,
            port=self.port,
            reload=False,
            log_config=None,
            log_level="info",
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, name="formflow-uvicorn", daemon=True)
        self.thread.start()

    def wait_until_listening(self, timeout_s: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if is_port_open(self.host, self.port):
                return True
            time.sleep(0.25)
        return False

    def stop(self, join_timeout_s: float = 5.0) -> bool:
        if self.server is not None:
            self.server.should_exit = True
        if self.thread is not None:
            self.thread.join(timeout=join_timeout_s)
            return not self.thread.is_alive()
        return True


def tray_menu_labels() -> list[str]:
    return [
        "Open FormFlow",
        "Server Status",
        "Re-check PreFormServer",
        "Restart FormFlow",
        "View Logs",
        "Quit",
    ]


def show_windows_dialog(title: str, message: str, *, question: bool = False) -> bool:
    try:
        import ctypes

        flags = 0x00000004 | 0x00000020 | 0x00040000 if question else 0x00000040 | 0x00040000
        result = ctypes.windll.user32.MessageBoxW(0, message, title, flags)
        return result in {1, 6}
    except Exception:
        return False


class FormFlowTrayRuntime:
    def __init__(
        self,
        *,
        paths: RuntimePaths,
        host: str,
        port: int,
        logger: Callable[[str], None],
        server_manager: FormFlowServerManager | None,
    ):
        self.paths = paths
        self.host = host
        self.port = port
        self.logger = logger
        self.server_manager = server_manager
        self.status = TrayStatus.CHECKING
        self.preform_payload: dict[str, Any] | None = None
        self.icon: Any = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def fetch_health(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.url}/health", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return response.status == 200 and payload.get("status") == "healthy"
        except Exception as exc:
            self.logger(f"health probe failed: {exc}")
            return False

    def fetch_preform_status(self) -> dict[str, Any] | None:
        try:
            with urllib.request.urlopen(f"{self.url}/api/preform-setup/status", timeout=3) as response:
                if response.status != 200:
                    return None
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            self.logger(f"PreForm status probe failed: {exc}")
            return None

    def refresh_status(self, *, checking: bool) -> TrayStatus:
        formflow_healthy = self.fetch_health() if not checking else False
        self.preform_payload = self.fetch_preform_status() if formflow_healthy else None
        self.status = decide_tray_status(
            formflow_healthy=formflow_healthy,
            preform_payload=self.preform_payload,
            checking=checking,
        )
        if self.icon is not None:
            self.icon.icon = create_tray_icon(self.status)
            self.icon.title = f"FormFlow ({self.status.value})"
        return self.status

    def open_formflow(self, *_args: Any) -> None:
        try:
            webbrowser.open_new(self.url)
        except Exception as exc:
            self.logger(f"browser open failed: {exc}")

    def show_status(self, *_args: Any) -> None:
        message = build_status_message(
            url=self.url,
            status=self.status,
            preform_payload=self.preform_payload,
            logs_dir=self.paths.logs_dir,
        )
        show_windows_dialog("FormFlow Status", message)

    def recheck_preform(self, *_args: Any) -> None:
        self.refresh_status(checking=True)
        request = urllib.request.Request(
            f"{self.url}/api/preform-setup/recheck",
            data=b"",
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10):
                pass
        except Exception as exc:
            self.logger(f"PreForm recheck failed: {exc}")
        self.refresh_status(checking=False)

    def restart_formflow(self, *_args: Any) -> None:
        if not show_windows_dialog(
            "Restart FormFlow",
            "Restart the local FormFlow server?",
            question=True,
        ):
            return
        self.refresh_status(checking=True)
        if self.server_manager is not None:
            stopped = self.server_manager.stop()
            if not stopped or is_port_open(self.host, self.port):
                self.logger("restart failed: server did not stop cleanly")
                self.status = TrayStatus.ERROR
                return
            self.server_manager.start()
            self.server_manager.wait_until_listening()
        self.refresh_status(checking=False)

    def view_logs(self, *_args: Any) -> None:
        self.paths.logs_dir.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(self.paths.logs_dir)])

    def quit(self, *_args: Any) -> None:
        if not show_windows_dialog(
            "Quit FormFlow",
            "Quit FormFlow and stop the local server?",
            question=True,
        ):
            return
        if self.server_manager is not None:
            self.server_manager.stop()
        if self.icon is not None:
            self.icon.stop()


def run_without_tray(manager: FormFlowServerManager) -> None:
    manager.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        manager.stop()


def main() -> None:
    paths = RuntimePaths.from_root(runtime_root())
    logger = create_diagnostic_logger(paths)
    try:
        _main(paths, logger)
    except Exception:
        logger("fatal startup error:")
        logger(traceback.format_exc())
        raise


def _main(paths: RuntimePaths, logger: Callable[[str], None]) -> None:
    logger("FormFlow tray runtime starting")
    host, port = configure_runtime_environment(paths)
    logger(f"runtime configured for {host}:{port}")

    def app_factory() -> Any:
        from app.main import app

        return app

    manager = FormFlowServerManager(host=host, port=port, app_factory=app_factory)
    runtime = FormFlowTrayRuntime(
        paths=paths,
        host=host,
        port=port,
        logger=logger,
        server_manager=manager,
    )

    try:
        import pystray
    except Exception as exc:
        logger(f"pystray unavailable, running without tray: {exc}")
        manager.start()
        manager.wait_until_listening()
        if os.environ.get("FORMFLOW_WEB_OPEN_BROWSER", "1").lower() not in {"0", "false", "no"}:
            runtime.open_formflow()
        run_without_tray(manager)
        return

    logger("pystray imported")
    menu = pystray.Menu(
        pystray.MenuItem("Open FormFlow", runtime.open_formflow, default=True),
        pystray.MenuItem("Server Status", runtime.show_status),
        pystray.MenuItem("Re-check PreFormServer", runtime.recheck_preform),
        pystray.MenuItem("Restart FormFlow", runtime.restart_formflow),
        pystray.MenuItem("View Logs", runtime.view_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", runtime.quit),
    )
    runtime.icon = pystray.Icon(
        "FormFlow",
        create_tray_icon(TrayStatus.CHECKING),
        "FormFlow (checking)",
        menu,
    )

    logger("starting uvicorn server")
    manager.start()

    def startup_probe() -> None:
        manager.wait_until_listening()
        logger("startup probe completed")
        runtime.refresh_status(checking=False)
        if os.environ.get("FORMFLOW_WEB_OPEN_BROWSER", "1").lower() not in {"0", "false", "no"}:
            runtime.open_formflow()

    threading.Thread(target=startup_probe, name="formflow-startup-probe", daemon=True).start()
    logger("starting tray icon loop")
    runtime.icon.run()
