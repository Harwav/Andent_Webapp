from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import time
import zipfile
from pathlib import Path
from uuid import uuid4

import requests

from ..config import Settings
from ..database import load_preform_setup_state, save_preform_setup_state
from ..schemas import PreFormSetupStatus


class PreFormSetupError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


PREFORM_PROBE_TIMEOUT_SECONDS = 2.0


def get_preform_setup_status(settings: Settings) -> PreFormSetupStatus:
    return PreFormSetupService(settings).recheck()


class PreFormSetupService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def install_from_zip(self, archive_path: Path) -> PreFormSetupStatus:
        self._validate_zip(archive_path)
        staging_root = self._extract_to_staging(archive_path)
        try:
            payload_root = self._resolve_payload_root(staging_root)
            self.stop(ignore_missing=True)
            self._replace_managed_install(payload_root)
            self._write_package_version_marker(archive_path)
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)
        return self.start()

    def replace_from_zip(self, archive_path: Path) -> PreFormSetupStatus:
        return self.install_from_zip(archive_path)

    def start(self) -> PreFormSetupStatus:
        executable = self.settings.preform_managed_executable
        if not executable.exists():
            raise PreFormSetupError(
                "missing_install",
                "Managed PreFormServer install is missing.",
            )

        state = load_preform_setup_state(self.settings)
        probe = self._probe_server()
        if probe["healthy"]:
            return self._persist_healthy_probe_status(
                probe,
                process_id=state.get("process_id"),
            )

        pid = self._launch_process(executable)
        return self._wait_for_server(pid)

    def stop(self, *, ignore_missing: bool = False) -> PreFormSetupStatus:
        state = load_preform_setup_state(self.settings)
        pid = state.get("process_id")
        if pid:
            try:
                self._terminate_process(int(pid))
            except Exception as exc:
                if not ignore_missing:
                    raise PreFormSetupError(
                        "stop_failed",
                        f"Could not stop managed PreFormServer process {pid}: {exc}",
                    ) from exc

        readiness = (
            "installed_not_running"
            if self.settings.preform_managed_executable.exists()
            else "not_installed"
        )
        return self._persist_status(
            readiness=readiness,
            detected_version=state.get("detected_version"),
            process_id=None,
            is_running=False,
            error_code=None,
            error_message=None,
        )

    def restart(self) -> PreFormSetupStatus:
        self.stop(ignore_missing=True)
        return self.start()

    def recheck(self) -> PreFormSetupStatus:
        state = load_preform_setup_state(self.settings)
        executable = self.settings.preform_managed_executable
        if not executable.exists():
            probe = self._probe_server()
            if probe["healthy"]:
                return self._persist_healthy_probe_status(probe, process_id=None)
            return self._persist_status(
                readiness="not_installed",
                detected_version=None,
                process_id=None,
                is_running=False,
                error_code=None,
                error_message=None,
            )

        probe = self._probe_server()
        if not probe["healthy"]:
            return self._persist_status(
                readiness="installed_not_running",
                detected_version=None,
                process_id=state.get("process_id"),
                is_running=False,
                error_code=str(probe["code"]),
                error_message=str(probe["message"]),
            )

        return self._persist_healthy_probe_status(
            probe,
            process_id=state.get("process_id"),
        )

    def _wait_for_server(self, pid: int) -> PreFormSetupStatus:
        deadline = time.monotonic() + self.settings.preform_server_startup_timeout_s
        last_probe = {
            "healthy": False,
            "version": None,
            "code": "start_failed",
            "message": "Timed out waiting for PreFormServer to become healthy.",
        }

        while time.monotonic() < deadline:
            probe = self._probe_server()
            if probe["healthy"]:
                return self._persist_healthy_probe_status(probe, process_id=pid)
            last_probe = probe
            time.sleep(1)

        return self._persist_status(
            readiness="installed_not_running",
            detected_version=self._read_managed_version(),
            process_id=pid,
            is_running=False,
            error_code=str(last_probe["code"]),
            error_message=str(last_probe["message"]),
        )

    def _persist_healthy_probe_status(
        self,
        probe: dict[str, object],
        *,
        process_id: object,
    ) -> PreFormSetupStatus:
        version = str(probe["version"])
        if not self._version_is_supported(version):
            return self._persist_status(
                readiness="incompatible_version",
                detected_version=version,
                process_id=self._coerce_process_id(process_id),
                is_running=True,
                error_code="incompatible_version",
                error_message=(
                    f"Detected PreFormServer {version} is outside the supported version contract."
                ),
            )

        return self._persist_status(
            readiness="ready",
            detected_version=version,
            process_id=self._coerce_process_id(process_id),
            is_running=True,
            error_code=None,
            error_message=None,
        )

    def _coerce_process_id(self, value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _persist_status(
        self,
        *,
        readiness: str,
        detected_version: str | None,
        process_id: int | None,
        is_running: bool,
        error_code: str | None,
        error_message: str | None,
    ) -> PreFormSetupStatus:
        state = save_preform_setup_state(
            self.settings,
            readiness=readiness,
            install_path=str(self.settings.preform_managed_dir),
            managed_executable_path=str(self.settings.preform_managed_executable),
            detected_version=detected_version,
            last_health_check_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            last_error_code=error_code,
            last_error_message=error_message,
            active_configured_source=True,
            process_id=process_id,
        )
        return PreFormSetupStatus(
            readiness=str(state["readiness"]),
            install_path=str(state["install_path"]),
            managed_executable_path=str(state["managed_executable_path"]),
            detected_version=(
                str(state["detected_version"])
                if state["detected_version"] is not None
                else None
            ),
            expected_version_min=self.settings.preform_min_supported_version,
            expected_version_max=self.settings.preform_max_supported_version,
            active_configured_source=bool(state["active_configured_source"]),
            is_running=is_running,
            last_health_check_at=(
                str(state["last_health_check_at"])
                if state["last_health_check_at"] is not None
                else None
            ),
            last_error_code=(
                str(state["last_error_code"])
                if state["last_error_code"] is not None
                else None
            ),
            last_error_message=(
                str(state["last_error_message"])
                if state["last_error_message"] is not None
                else None
            ),
        )

    def _validate_zip(self, archive_path: Path) -> None:
        if not archive_path.exists():
            raise PreFormSetupError("bad_zip", "Selected ZIP file does not exist.")
        if archive_path.suffix.lower() != ".zip":
            raise PreFormSetupError("bad_zip", "Select a .zip package for PreFormServer.")
        if archive_path.stat().st_size < self.settings.preform_min_zip_size_bytes:
            raise PreFormSetupError(
                "bad_zip",
                "Selected ZIP is smaller than the minimum supported package size.",
            )

        try:
            with zipfile.ZipFile(archive_path) as archive:
                members = [
                    Path(member.filename)
                    for member in archive.infolist()
                    if not member.is_dir()
                ]
        except zipfile.BadZipFile as exc:
            raise PreFormSetupError("bad_zip", "Selected ZIP archive is corrupt.") from exc

        if not members:
            raise PreFormSetupError("bad_zip", "Selected ZIP archive is empty.")

        for member in members:
            if member.is_absolute() or ".." in member.parts:
                raise PreFormSetupError(
                    "bad_zip",
                    "Selected ZIP uses an unsupported package shape.",
                )

        if "PreFormServer.exe" not in {member.name for member in members}:
            raise PreFormSetupError(
                "bad_zip",
                "ZIP does not contain a supported PreFormServer.exe payload.",
            )

    def _extract_to_staging(self, archive_path: Path) -> Path:
        staging_root = (
            self.settings.preform_managed_dir.parent / f".preform-staging-{uuid4().hex}"
        )
        staging_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(staging_root)
        return staging_root

    def _resolve_payload_root(self, staging_root: Path) -> Path:
        candidates = list(staging_root.rglob("PreFormServer.exe"))
        if not candidates:
            raise PreFormSetupError(
                "bad_zip",
                "Staged package does not contain PreFormServer.exe.",
            )
        if len(candidates) > 1:
            raise PreFormSetupError(
                "bad_zip",
                "ZIP contains multiple PreFormServer.exe candidates.",
            )

        executable_path = candidates[0]
        relative_parts = executable_path.relative_to(staging_root).parts
        if len(relative_parts) == 1:
            return staging_root
        if len(relative_parts) == 2:
            return staging_root / relative_parts[0]
        raise PreFormSetupError(
            "bad_zip",
            "ZIP uses an unsupported nested package layout.",
        )

    def _replace_managed_install(self, payload_root: Path) -> None:
        managed_dir = self.settings.preform_managed_dir
        managed_dir.parent.mkdir(parents=True, exist_ok=True)
        backup_dir = managed_dir.parent / f".preform-backup-{uuid4().hex}"

        if managed_dir.exists():
            managed_dir.rename(backup_dir)

        try:
            payload_root.rename(managed_dir)
        except Exception as exc:
            if backup_dir.exists() and not managed_dir.exists():
                backup_dir.rename(managed_dir)
            raise PreFormSetupError(
                "install_failed",
                f"Could not replace the managed PreFormServer install: {exc}",
            ) from exc
        finally:
            shutil.rmtree(backup_dir, ignore_errors=True)

    def _write_package_version_marker(self, archive_path: Path) -> None:
        version_file = self.settings.preform_managed_dir / "version.txt"
        if version_file.exists():
            return
        version = self._extract_version(archive_path.stem)
        if not version:
            return
        version_file.write_text(version, encoding="utf-8")

    def _launch_process(self, executable_path: Path) -> int:
        resolved_executable = executable_path.resolve(strict=True)
        resolved_managed_dir = self.settings.preform_managed_dir.resolve(strict=True)
        args = [
            str(resolved_executable),
            "--port",
            str(self.settings.preform_server_port),
        ]
        env = os.environ.copy()
        runtime_paths = [
            str(resolved_managed_dir),
            str((resolved_managed_dir / "hoops").resolve(strict=False)),
        ]
        env["PATH"] = os.pathsep.join(runtime_paths + [env.get("PATH", "")])
        creation_flags = 0
        if os.name == "nt":
            creation_flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                0,
            )

        process = subprocess.Popen(
            args,
            cwd=str(resolved_managed_dir),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        return int(process.pid)

    def _terminate_process(self, pid: int) -> None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return
        os.kill(pid, signal.SIGTERM)

    def _probe_server(self) -> dict[str, object]:
        session = requests.Session()
        version = self._read_managed_version()
        last_error = {
            "healthy": False,
            "version": version,
            "code": "health_check_failed",
            "message": "PreFormServer local API is not reachable.",
        }
        for endpoint in ("/", "/scene/"):
            url = f"{self.settings.preform_server_url.rstrip('/')}{endpoint}"
            try:
                response = session.get(url, timeout=PREFORM_PROBE_TIMEOUT_SECONDS)
            except requests.RequestException as exc:
                last_error = {
                    "healthy": False,
                    "version": None,
                    "code": "health_check_failed",
                    "message": str(exc),
                }
                continue

            if not response.ok:
                last_error = {
                    "healthy": False,
                    "version": None,
                    "code": "health_check_failed",
                    "message": f"Server returned {response.status_code}.",
                }
                continue

            payload = self._load_response_payload(response)
            detected_version = self._extract_version(payload) or version
            if detected_version is None:
                detected_version = "0.0.0"
            session.close()
            return {
                "healthy": response.ok or response.status_code < 500,
                "version": detected_version,
                "code": None,
                "message": None,
            }

        session.close()
        return last_error

    def _read_managed_version(self) -> str | None:
        version_file = self.settings.preform_managed_dir / "version.txt"
        if version_file.exists():
            version = version_file.read_text(encoding="utf-8").strip()
            if version:
                return version
        return self._read_managed_executable_version()

    def _read_managed_executable_version(self) -> str | None:
        executable = self.settings.preform_managed_executable
        if os.name != "nt" or not executable.exists():
            return None
        try:
            import ctypes
            from ctypes import wintypes

            executable_path = str(executable.resolve())
            size = ctypes.windll.version.GetFileVersionInfoSizeW(executable_path, None)
            if not size:
                return None
            buffer = ctypes.create_string_buffer(size)
            ctypes.windll.version.GetFileVersionInfoW(executable_path, 0, size, buffer)
            pointer = ctypes.c_void_p()
            length = wintypes.UINT()
            ctypes.windll.version.VerQueryValueW(
                buffer,
                "\\",
                ctypes.byref(pointer),
                ctypes.byref(length),
            )

            class _FixedFileInfo(ctypes.Structure):
                _fields_ = [
                    ("dwSignature", wintypes.DWORD),
                    ("dwStrucVersion", wintypes.DWORD),
                    ("dwFileVersionMS", wintypes.DWORD),
                    ("dwFileVersionLS", wintypes.DWORD),
                    ("dwProductVersionMS", wintypes.DWORD),
                    ("dwProductVersionLS", wintypes.DWORD),
                    ("dwFileFlagsMask", wintypes.DWORD),
                    ("dwFileFlags", wintypes.DWORD),
                    ("dwFileOS", wintypes.DWORD),
                    ("dwFileType", wintypes.DWORD),
                    ("dwFileSubtype", wintypes.DWORD),
                    ("dwFileDateMS", wintypes.DWORD),
                    ("dwFileDateLS", wintypes.DWORD),
                ]

            info = ctypes.cast(pointer, ctypes.POINTER(_FixedFileInfo)).contents
            parts = (
                info.dwFileVersionMS >> 16,
                info.dwFileVersionMS & 0xFFFF,
                info.dwFileVersionLS >> 16,
                info.dwFileVersionLS & 0xFFFF,
            )
            if any(parts):
                return ".".join(str(part) for part in parts)
        except Exception:
            return None
        return None

    def _load_response_payload(self, response: requests.Response) -> object:
        try:
            return response.json()
        except ValueError:
            return response.text

    def _extract_version(self, payload: object) -> str | None:
        if isinstance(payload, dict):
            for key in (
                "version",
                "build_version",
                "preform_version",
                "server_version",
            ):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for value in payload.values():
                detected = self._extract_version(value)
                if detected:
                    return detected
            return None

        if isinstance(payload, list):
            for item in payload:
                detected = self._extract_version(item)
                if detected:
                    return detected
            return None

        if isinstance(payload, str):
            match = re.search(r"\d+\.\d+\.\d+(?:\.\d+)?", payload)
            return match.group(0) if match else None

        return None

    def _version_is_supported(self, version: str) -> bool:
        version_tuple = self._version_tuple(version)
        if version_tuple < self._version_tuple(self.settings.preform_min_supported_version):
            return False
        if self.settings.preform_max_supported_version and version_tuple > self._version_tuple(
            self.settings.preform_max_supported_version
        ):
            return False
        return True

    def _version_tuple(self, value: str) -> tuple[int, ...]:
        numbers = [int(part) for part in re.findall(r"\d+", value)]
        if not numbers:
            return (0,)
        return tuple(numbers)
