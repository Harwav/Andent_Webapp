# FormFlow Tray Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current console-only Windows EXE launcher with a robust YF_ERP-style tray runtime that shows green/yellow/red readiness, exposes a right-click menu, and shuts down cleanly.

**Architecture:** Move tray/server lifecycle logic into a testable `desktop/tray_runtime.py` module. Keep `run_formflow.py` as a thin entrypoint that calls the runtime. Package the same entrypoint with PyInstaller using `console=False`, `pystray`, `Pillow`, and explicit hidden imports.

**Tech Stack:** Python 3.13, FastAPI, uvicorn `Server`, pystray, Pillow, PyInstaller, pytest, PowerShell smoke tests.

---

## File Map

| File | Action | Responsibility |
| --- | --- | --- |
| `desktop/__init__.py` | Create | Desktop runtime package marker |
| `desktop/tray_runtime.py` | Create | Runtime paths, logging, status model, icon rendering, uvicorn server manager, probes, tray controller |
| `run_formflow.py` | Modify | Thin launcher: `from desktop.tray_runtime import main; main()` |
| `requirements.txt` | Modify | Add packaged runtime dependencies: `requests`, `pystray`, `Pillow`, `pyinstaller` |
| `formflow.spec` | Modify | Hidden imports for tray deps, include `desktop`, set `console=False` |
| `.github/workflows/build-windows-exe.yml` | Modify | Add import audit and tray-aware EXE cleanup |
| `.codex/skills/formflow-release/SKILL.md` | Modify | Add tray smoke-test/release steps |
| `tests/test_tray_runtime.py` | Create | Unit tests for status model, runtime env, logging, menu labels, server shutdown behavior |

---

### Task 1: Status Model, Runtime Paths, and Early Logging

**Files:**
- Create: `desktop/__init__.py`
- Create: `desktop/tray_runtime.py`
- Test: `tests/test_tray_runtime.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_tray_runtime.py` with these tests:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests/test_tray_runtime.py -q
```

Expected: import failure because `desktop.tray_runtime` does not exist.

- [ ] **Step 3: Implement the status/path/logging foundation**

Create `desktop/__init__.py`:

```python
"""Desktop runtime support for the packaged FormFlow app."""
```

Create the initial `desktop/tray_runtime.py`:

```python
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable


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
        f"Logs: {logs_dir}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests/test_tray_runtime.py -q
```

Expected: all tests in `tests/test_tray_runtime.py` pass.

- [ ] **Step 5: Commit**

```powershell
git add desktop/__init__.py desktop/tray_runtime.py tests/test_tray_runtime.py
git commit -m "Add testable FormFlow tray runtime foundation" `
  -m "Introduce status decisions, packaged runtime paths, and early diagnostic logging before adding tray or server lifecycle behavior." `
  -m "Constraint: Tray runtime must remain independent of backend business logic" `
  -m "Confidence: high" `
  -m "Scope-risk: narrow" `
  -m "Tested: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_tray_runtime.py -q"
```

---

### Task 2: Icon Rendering, Probe Client, and Server Lifecycle

**Files:**
- Modify: `desktop/tray_runtime.py`
- Modify: `tests/test_tray_runtime.py`

- [ ] **Step 1: Add failing tests**

Append these tests to `tests/test_tray_runtime.py`:

```python
import socket

from desktop.tray_runtime import (
    FormFlowServerManager,
    create_tray_icon,
    is_port_open,
)


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests/test_tray_runtime.py -q
```

Expected: failures for missing `create_tray_icon`, `is_port_open`, and `FormFlowServerManager`.

- [ ] **Step 3: Implement icon rendering, port checks, and lifecycle manager**

Add this code to `desktop/tray_runtime.py` below `build_status_message`:

```python
import socket
import threading
import time

import uvicorn
from PIL import Image, ImageDraw


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests/test_tray_runtime.py -q
```

Expected: all tests in `tests/test_tray_runtime.py` pass.

- [ ] **Step 5: Commit**

```powershell
git add desktop/tray_runtime.py tests/test_tray_runtime.py
git commit -m "Add tray icon and uvicorn lifecycle primitives" `
  -m "Use explicit uvicorn.Server ownership so tray restart and quit can request shutdown and wait for the server thread." `
  -m "Rejected: Continue using blocking uvicorn.run | cannot support robust tray restart or quit" `
  -m "Confidence: high" `
  -m "Scope-risk: moderate" `
  -m "Tested: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_tray_runtime.py -q"
```

---

### Task 3: Tray Controller and Menu Actions

**Files:**
- Modify: `desktop/tray_runtime.py`
- Modify: `tests/test_tray_runtime.py`

- [ ] **Step 1: Add failing tests for menu labels and status refresh behavior**

Append these tests to `tests/test_tray_runtime.py`:

```python
from desktop.tray_runtime import FormFlowTrayRuntime, tray_menu_labels


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
    runtime.fetch_preform_status = lambda: {"readiness": "ready", "detected_version": "3.58.1.627"}

    runtime.refresh_status(checking=False)

    assert runtime.status == TrayStatus.READY
    assert runtime.preform_payload["readiness"] == "ready"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests/test_tray_runtime.py -q
```

Expected: failures for missing `FormFlowTrayRuntime` and `tray_menu_labels`.

- [ ] **Step 3: Implement tray controller without business logic**

Add these imports near the top of `desktop/tray_runtime.py`:

```python
import json
import subprocess
import urllib.error
import urllib.request
import webbrowser
```

Add this code below `FormFlowServerManager`:

```python
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
        if not show_windows_dialog("Restart FormFlow", "Restart the local FormFlow server?", question=True):
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
        if not show_windows_dialog("Quit FormFlow", "Quit FormFlow and stop the local server?", question=True):
            return
        if self.server_manager is not None:
            self.server_manager.stop()
        if self.icon is not None:
            self.icon.stop()
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests/test_tray_runtime.py -q
```

Expected: all tests in `tests/test_tray_runtime.py` pass.

- [ ] **Step 5: Commit**

```powershell
git add desktop/tray_runtime.py tests/test_tray_runtime.py
git commit -m "Add FormFlow tray controller actions" `
  -m "Wire status refresh, POST-based PreForm recheck, browser/log/status actions, restart, and quit behind a testable tray controller." `
  -m "Constraint: Recheck must call POST /api/preform-setup/recheck" `
  -m "Confidence: high" `
  -m "Scope-risk: moderate" `
  -m "Tested: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_tray_runtime.py -q"
```

---

### Task 4: Entry Point, Dependencies, and PyInstaller Packaging

**Files:**
- Modify: `run_formflow.py`
- Modify: `requirements.txt`
- Modify: `formflow.spec`
- Modify: `desktop/tray_runtime.py`

- [ ] **Step 1: Add final runtime `main()` and pystray wiring**

Add this function to `desktop/tray_runtime.py`:

```python
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
    logger("FormFlow tray runtime starting")
    host, port = configure_runtime_environment(paths)

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

    manager.start()

    def startup_probe() -> None:
        manager.wait_until_listening()
        runtime.refresh_status(checking=False)
        if os.environ.get("FORMFLOW_WEB_OPEN_BROWSER", "1").lower() not in {"0", "false", "no"}:
            runtime.open_formflow()

    threading.Thread(target=startup_probe, name="formflow-startup-probe", daemon=True).start()
    runtime.icon.run()
```

- [ ] **Step 2: Replace `run_formflow.py` with a thin launcher**

Replace `run_formflow.py` with:

```python
from __future__ import annotations

from desktop.tray_runtime import main


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Update `requirements.txt`**

Replace `requirements.txt` with:

```text
# Andent Web Phase 0 Requirements

fastapi==0.115.6
uvicorn[standard]==0.34.0
python-multipart==0.0.18
pydantic==2.10.3
numpy-stl>=3.1.1
httpx==0.28.1
requests==2.32.3
pytest>=8.0.0,<9.0.0

# Windows EXE packaging/runtime
Pillow==10.4.0
pystray==0.19.5
pyinstaller==6.14.2
```

- [ ] **Step 4: Update `formflow.spec`**

Modify `formflow.spec` so hidden imports include `desktop`, tray deps, and `requests`, and set `console=False`:

```python
for package in ("app", "core", "desktop", "uvicorn", "anyio", "requests"):
    hiddenimports.extend(collect_submodules(package))

hiddenimports.extend([
    "pystray",
    "pystray._win32",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
])
```

Change:

```python
console=True,
```

to:

```python
console=False,
```

- [ ] **Step 5: Run dependency/import checks**

Run:

```powershell
python -m pip install -r requirements.txt
python -c "import app.main; import desktop.tray_runtime; print('imports ok')"
```

Expected: dependencies install and command prints `imports ok`.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests/test_tray_runtime.py tests/test_exe_packaging.py tests/test_health_endpoints.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```powershell
git add run_formflow.py desktop/tray_runtime.py requirements.txt formflow.spec
git commit -m "Package FormFlow as a tray desktop runtime" `
  -m "Switch the executable entrypoint from a blocking console server to a pystray-owned desktop runtime with explicit dependencies and hidden imports." `
  -m "Constraint: Customer-facing EXE must run with console=False while still logging startup failures to disk" `
  -m "Confidence: high" `
  -m "Scope-risk: moderate" `
  -m "Tested: import audit and focused tray/packaging/health tests"
```

---

### Task 5: CI, Skill Guidance, and Packaged EXE Smoke Test

**Files:**
- Modify: `.github/workflows/build-windows-exe.yml`
- Modify: `.codex/skills/formflow-release/SKILL.md`

- [ ] **Step 1: Add workflow import audit before build**

In `.github/workflows/build-windows-exe.yml`, add this step after dependency installation:

```yaml
      - name: Import audit
        shell: pwsh
        run: python -c "import app.main; import desktop.tray_runtime; print('imports ok')"
```

- [ ] **Step 2: Make smoke cleanup tray-aware**

In the smoke test `finally` block, keep both cleanup paths:

```powershell
Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
Get-Process | Where-Object { $_.Path -eq (Resolve-Path $exe).Path } |
  Stop-Process -Force -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
if (Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue) {
  throw "Port 8765 was still open after EXE cleanup"
}
```

- [ ] **Step 3: Update the release skill**

In `.codex/skills/formflow-release/SKILL.md`, add tray-specific checks:

```markdown
6. For tray releases, launch the EXE normally on a Windows desktop and verify:
   - a tray icon appears
   - right-click menu contains Open FormFlow, Server Status, Re-check PreFormServer, Restart FormFlow, View Logs, and Quit
   - no usable PreFormServer turns the icon red after startup
   - a ready live PreFormServer turns the icon green
   - Quit closes the EXE and releases the port
```

- [ ] **Step 4: Build the EXE**

Run:

```powershell
python scripts/builders/build_windows_exe.py
```

Expected: `dist/FormFlow_v0.1.0.exe` is created.

- [ ] **Step 5: Smoke test the EXE health endpoint**

Run:

```powershell
$exe = Resolve-Path "dist\FormFlow_v0.1.0.exe"
$env:FORMFLOW_WEB_PORT = "8765"
$env:FORMFLOW_WEB_OPEN_BROWSER = "0"
$process = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden
try {
  $healthy = $false
  for ($i = 0; $i -lt 60; $i++) {
    try {
      $response = Invoke-RestMethod -Uri "http://127.0.0.1:8765/health" -TimeoutSec 2
      if ($response.status -eq "healthy") {
        $healthy = $true
        break
      }
    } catch {
      Start-Sleep -Seconds 1
    }
  }
  if (-not $healthy) {
    throw "EXE did not become healthy on port 8765"
  }
} finally {
  Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
  Get-Process | Where-Object { $_.Path -eq $exe.Path } | Stop-Process -Force -ErrorAction SilentlyContinue
  Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
  Remove-Item Env:\FORMFLOW_WEB_PORT -ErrorAction SilentlyContinue
  Remove-Item Env:\FORMFLOW_WEB_OPEN_BROWSER -ErrorAction SilentlyContinue
}
```

Expected: health returns `healthy`; cleanup leaves no `FormFlow_v0.1.0.exe` process and no listener on port `8765`.

- [ ] **Step 6: Run full tests**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest tests/ -q
```

Expected: full test suite passes, with existing skipped tests unchanged.

- [ ] **Step 7: Commit**

```powershell
git add .github/workflows/build-windows-exe.yml .codex/skills/formflow-release/SKILL.md
git commit -m "Harden FormFlow tray release automation" `
  -m "Add import auditing, stale process cleanup checks, and tray-specific release verification guidance for future Windows builds." `
  -m "Constraint: Release automation must detect missing packaged dependencies before PyInstaller builds" `
  -m "Confidence: high" `
  -m "Scope-risk: narrow" `
  -m "Tested: build_windows_exe smoke test and full pytest suite"
```

---

## Self-Review

Spec coverage:
- Status model is implemented in Tasks 1 and 2.
- Tray menu and callbacks are implemented in Task 3.
- Uvicorn lifecycle robustness is implemented in Task 2 and exercised in Task 5 smoke cleanup.
- Packaging dependencies and `console=False` are implemented in Task 4.
- CI/release skill hardening is implemented in Task 5.
- Live PreFormServer proof remains a manual/live verification requirement, not an automated CI claim.

Placeholder scan:
- No deferred implementation markers are intentionally present.

Type consistency:
- `TrayStatus`, `RuntimePaths`, `FormFlowServerManager`, and `FormFlowTrayRuntime` names are introduced before use and reused consistently.
