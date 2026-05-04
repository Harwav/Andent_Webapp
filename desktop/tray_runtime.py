from __future__ import annotations

import os
import socket
import sys
import threading
import time
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
