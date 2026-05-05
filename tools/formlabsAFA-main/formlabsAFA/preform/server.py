from __future__ import annotations

import os
import queue
import shlex
import subprocess
import sys
import threading
from pathlib import Path

import psutil
import requests


def find_preform_server_path(override: str = "") -> Path:
    if override:
        path = Path(override)
        if not path.is_file():
            raise FileNotFoundError(
                f"PreFormServer not found at {path}"
            )
        return path

    if sys.platform == "win32":
        path = Path.cwd() / "PreForm_Server" / "PreFormServer.exe"
    elif sys.platform == "darwin":
        path = (
            Path.cwd()
            / "PreForm_Server"
            / "PreFormServer.app"
            / "Contents"
            / "MacOS"
            / "PreFormServer"
        )
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")

    if not path.is_file():
        raise FileNotFoundError(f"PreFormServer not found at {path}")
    return path


class PreFormServer:
    def __init__(self, port: int, process: subprocess.Popen | None = None):
        self.port = port
        self._process = process
        self._we_started_it = process is not None

    @classmethod
    def start(
        cls,
        path: Path | None = None,
        port: int = 44388,
    ) -> PreFormServer:
        server_path = path or find_preform_server_path()
        command_str = f"{server_path} --port {port}"
        process_args = (
            command_str if sys.platform == "win32" else shlex.split(command_str)
        )
        process = subprocess.Popen(
            process_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        outq: queue.Queue[str] = queue.Queue()

        def reader(proc: subprocess.Popen, q: queue.Queue) -> None:
            assert proc.stdout is not None
            for line in iter(proc.stdout.readline, ""):
                q.put(line)

        t = threading.Thread(target=reader, args=(process, outq), daemon=True)
        t.start()

        max_attempts = 10
        for attempt in range(max_attempts):
            try:
                line = outq.get(block=True, timeout=60)
                if "READY FOR INPUT" in line:
                    return cls(port, process)
                if "address is already in use" in line:
                    process.terminate()
                    raise RuntimeError(
                        f"Port {port} already in use -- another PreForm Server may be running."
                    )
                if "error" in line.lower() or "fatal" in line.lower():
                    logger.warning("PreForm Server output: %s", line.strip())
            except queue.Empty:
                if process.poll() is not None:
                    process.terminate()
                    raise RuntimeError(
                        f"PreForm Server exited unexpectedly (code {process.returncode})"
                    )

        process.terminate()
        raise TimeoutError(
            f"PreForm Server did not become ready after {max_attempts} attempts"
        )

    @classmethod
    def connect(cls, port: int = 44388) -> PreFormServer:
        process = cls._find_process_on_port(port)
        if process is None:
            raise RuntimeError(f"No PreForm Server found on port {port}")
        cls._check_valid_server(port)
        return cls(port)

    @classmethod
    def start_or_connect(
        cls,
        path: Path | None = None,
        port: int = 44388,
    ) -> PreFormServer:
        existing = cls._find_process_on_port(port)
        if existing is not None:
            cls._check_valid_server(port)
            return cls(port)
        return cls.start(path, port)

    def stop(self) -> None:
        if self._process is not None and self._we_started_it:
            self._process.terminate()
            self._process.wait()
            self._process = None

    def __enter__(self) -> PreFormServer:
        return self

    def __exit__(self, *args) -> None:
        self.stop()

    @staticmethod
    def _find_process_on_port(port: int) -> psutil.Process | None:
        for proc in psutil.process_iter():
            try:
                for conn in proc.connections():
                    if conn.laddr.port == port:
                        return proc
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass
        return None

    @staticmethod
    def _check_valid_server(port: int) -> None:
        try:
            resp = requests.get(f"http://localhost:{port}", timeout=5)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(
                f"Process on port {port} is not a valid PreForm Server: {e}"
            )
        if data is None or data.get("version") is None:
            raise RuntimeError(
                f"Process on port {port} is not a valid PreForm Server"
            )
