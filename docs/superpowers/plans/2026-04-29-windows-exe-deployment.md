# Windows EXE Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package FormFlow as a single Windows EXE that a non-technical dental lab technician can download, double-click, and be fully running within minutes — including a browser-based first-run setup wizard for PreFormServer, a system tray icon, and an auto-updater.

**Architecture:** PyInstaller bundles the FastAPI app + uvicorn + pystray into one EXE. `run_tray.py` is the entry point: it configures AppData paths, starts uvicorn in a background thread, shows a system tray icon, and opens the browser to `/setup` (first run) or `/` (subsequent runs). A second small updater EXE (`FormFlow_Updater.exe`) is bundled inside the main EXE and launched detached during self-update to swap the binary while the main process exits.

**Tech Stack:** PyInstaller 6.x, pystray 0.19.x, Pillow 10.x, psutil 6.x, uvicorn, FastAPI (existing), Python 3.13 (CI build)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/version.py` | Create | Single source of truth for `__version__` |
| `app/routers/setup.py` | Create | `GET /setup` wizard page + `GET /api/setup/lan-ip` |
| `app/static/setup.html` | Create | Browser-based 3-step setup wizard UI |
| `app/static/tray_icon.png` | Create | 64×64 green circle PNG for tray |
| `app/main.py` | Modify | Register setup router; set `app.state.lan_ip` |
| `requirements.txt` | Modify | Add pystray, Pillow, psutil |
| `run_tray.py` | Create | EXE entry point: env vars, uvicorn thread, tray, updater |
| `scripts/updater.py` | Create | Updater helper: wait for PID exit, replace EXE, relaunch |
| `scripts/builders/build_deployment.py` | Create | Version bump → PyInstaller run for both specs |
| `formflow.spec` | Create | PyInstaller spec for main EXE |
| `formflow_updater.spec` | Create | PyInstaller spec for updater EXE |
| `version_info.txt` | Create | Windows EXE metadata |
| `.github/workflows/build-windows.yml` | Create | CI: tag push → build → GitHub Release |

---

## Task 1: Version File

**Files:**
- Create: `app/version.py`

- [ ] **Step 1: Create `app/version.py`**

```python
__version__ = "1.0.0"
```

- [ ] **Step 2: Commit**

```bash
git add app/version.py
git commit -m "feat: add version file"
```

---

## Task 2: Add pystray, Pillow, psutil to requirements

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add dependencies to `requirements.txt`**

```
# FormFlow Phase 0 Requirements

fastapi==0.115.6
uvicorn[standard]==0.34.0
python-multipart==0.0.18
pydantic==2.10.3
numpy-stl>=3.1.1
httpx==0.28.1
pytest>=8.0.0,<9.0.0

# Desktop packaging
pystray==0.19.5
Pillow==10.4.0
psutil==6.1.1
pyinstaller==6.11.1
```

- [ ] **Step 2: Install new dependencies**

```bash
pip install pystray==0.19.5 Pillow==10.4.0 psutil==6.1.1 pyinstaller==6.11.1
```

Expected: all four packages install without errors.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat: add pystray, Pillow, psutil, pyinstaller to requirements"
```

---

## Task 3: Tray Icon Asset

**Files:**
- Create: `app/static/tray_icon.png`

- [ ] **Step 1: Generate green circle PNG via Python**

Run this one-time script in a Python REPL or terminal (does not need to be committed):

```python
from PIL import Image, ImageDraw

img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
draw.ellipse([4, 4, 60, 60], fill=(12, 141, 58, 255))  # --clear color from styles.css
img.save("app/static/tray_icon.png")
```

- [ ] **Step 2: Verify file exists**

```bash
python -c "from PIL import Image; img = Image.open('app/static/tray_icon.png'); print(img.size, img.mode)"
```

Expected: `(64, 64) RGBA`

- [ ] **Step 3: Commit**

```bash
git add app/static/tray_icon.png
git commit -m "feat: add tray icon asset"
```

---

## Task 4: Setup Router (backend)

**Files:**
- Create: `app/routers/setup.py`
- Test: `tests/test_setup_router.py`

The setup router serves two things: the `/setup` HTML page (with a redirect guard) and a `/api/setup/lan-ip` JSON endpoint so the setup wizard can display the LAN address without knowing it at HTML-generation time.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_setup_router.py`:

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.config import get_settings


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FORMFLOW_WEB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FORMFLOW_WEB_DATABASE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    app = create_app()
    app.state.lan_ip = "192.168.1.100"
    with TestClient(app, follow_redirects=False) as c:
        yield c


def test_lan_ip_endpoint_returns_json(client):
    resp = client.get("/api/setup/lan-ip")
    assert resp.status_code == 200
    data = resp.json()
    assert data["lan_ip"] == "192.168.1.100"
    assert data["port"] == 8090


def test_setup_page_redirects_when_ready(client, monkeypatch):
    from app.database import save_preform_setup_state
    from app.config import get_settings
    save_preform_setup_state(get_settings(), readiness="ready")
    resp = client.get("/setup")
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"


def test_setup_page_serves_html_when_not_installed(client):
    resp = client.get("/setup")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert b"setup" in resp.content.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_setup_router.py -v
```

Expected: 3 failures — `ImportError: cannot import name 'router' from 'app.routers.setup'` or similar.

- [ ] **Step 3: Create `app/routers/setup.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse

from ..database import load_preform_setup_state

router = APIRouter()


@router.get("/setup", include_in_schema=False)
async def setup_page(request: Request):
    settings = request.app.state.settings
    state = load_preform_setup_state(settings)
    if state.get("readiness") == "ready":
        return RedirectResponse(url="/", status_code=302)
    return FileResponse(settings.static_dir / "setup.html")


@router.get("/api/setup/lan-ip")
async def lan_ip(request: Request) -> dict:
    return {
        "lan_ip": getattr(request.app.state, "lan_ip", "127.0.0.1"),
        "port": request.app.state.settings.server_port,
    }
```

- [ ] **Step 4: Register the router in `app/main.py`**

Add the import after the existing router imports:

```python
from .routers.setup import router as setup_router
```

Add `app.include_router(setup_router)` inside `create_app()`, after the existing `app.include_router(print_queue_router)` line:

```python
    app.include_router(uploads_router)
    app.include_router(metrics_router)
    app.include_router(preform_setup_router)
    app.include_router(print_queue_router)
    app.include_router(setup_router)
```

Also set a default `lan_ip` on `app.state` so it works in tests and dev:

```python
    app.state.settings = resolved_settings
    app.state.default_print_dispatch_mode = resolved_settings.print_dispatch_mode
    app.state.lan_ip = "127.0.0.1"  # overwritten by run_tray.py at EXE startup
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_setup_router.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q
```

Expected: all existing tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/routers/setup.py app/main.py tests/test_setup_router.py
git commit -m "feat: add setup router with wizard page and lan-ip endpoint"
```

---

## Task 5: Setup Wizard HTML

**Files:**
- Create: `app/static/setup.html`

This is a single HTML file with embedded CSS (importing `styles.css`) and vanilla JS. It has three steps managed by CSS class toggling (no framework). It uses the existing `/api/preform-setup/install-from-zip` endpoint and polls `/api/preform-setup/status`.

- [ ] **Step 1: Create `app/static/setup.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>FormFlow — Setup</title>
  <link rel="stylesheet" href="/static/styles.css" />
  <style>
    .setup-shell {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: var(--bg);
    }
    .setup-card {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 12px;
      box-shadow: var(--shadow);
      padding: 48px 56px;
      width: 100%;
      max-width: 520px;
    }
    .setup-logo {
      font-family: var(--font-display);
      font-size: 1.6rem;
      font-weight: 700;
      color: var(--ink);
      margin-bottom: 8px;
    }
    .setup-step { display: none; }
    .setup-step.active { display: block; }
    .setup-title {
      font-family: var(--font-display);
      font-size: 1.4rem;
      font-weight: 600;
      margin: 24px 0 8px;
    }
    .setup-body {
      color: var(--muted);
      font-size: 0.95rem;
      line-height: 1.6;
      margin-bottom: 28px;
    }
    .setup-btn {
      display: inline-block;
      background: var(--accent);
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 12px 28px;
      font-size: 1rem;
      font-family: var(--font-ui);
      cursor: pointer;
      text-decoration: none;
    }
    .setup-btn:hover { background: var(--accent-dark); }
    .setup-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .drop-zone {
      border: 2px dashed var(--line);
      border-radius: 8px;
      padding: 36px 24px;
      text-align: center;
      color: var(--muted);
      cursor: pointer;
      margin-bottom: 20px;
      transition: border-color 0.15s, background 0.15s;
    }
    .drop-zone.over {
      border-color: var(--accent);
      background: var(--accent-soft);
    }
    .drop-zone.has-file {
      border-color: var(--clear);
      background: var(--clear-soft);
      color: var(--clear);
    }
    #file-input { display: none; }
    .status-msg {
      margin-top: 16px;
      padding: 12px 16px;
      border-radius: 6px;
      font-size: 0.9rem;
    }
    .status-msg.error { background: var(--danger-soft); color: var(--danger); }
    .status-msg.info  { background: var(--info-soft);   color: var(--info); }
    .status-msg.ok    { background: var(--clear-soft);  color: var(--clear); }
    .lan-box {
      background: var(--surface-soft);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px 20px;
      font-family: monospace;
      font-size: 1rem;
      color: var(--info);
      margin: 16px 0 28px;
    }
    .spinner {
      display: inline-block;
      width: 18px; height: 18px;
      border: 3px solid var(--line);
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
      vertical-align: middle;
      margin-right: 8px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
<div class="setup-shell">
  <div class="setup-card">
    <div class="setup-logo">FormFlow</div>

    <!-- Step 1: Welcome -->
    <div class="setup-step active" id="step-1">
      <div class="setup-title">Welcome</div>
      <div class="setup-body">
        FormFlow manages your dental 3D print workflow. Before you begin,
        you'll need the <strong>PreFormServer ZIP</strong> from Formlabs.
        Download it from the Formlabs Dashboard, then click Get Started.
      </div>
      <button class="setup-btn" onclick="goStep(2)">Get Started &rarr;</button>
    </div>

    <!-- Step 2: Install PreFormServer -->
    <div class="setup-step" id="step-2">
      <div class="setup-title">Install PreFormServer</div>
      <div class="setup-body">
        Drag and drop the PreFormServer ZIP here, or click to browse.
      </div>
      <div class="drop-zone" id="drop-zone" onclick="document.getElementById('file-input').click()">
        <span id="drop-label">Drop PreFormServer.zip here or click to browse</span>
        <input type="file" id="file-input" accept=".zip" />
      </div>
      <button class="setup-btn" id="install-btn" disabled onclick="installZip()">Install</button>
      <div id="status-msg" style="display:none" class="status-msg"></div>
    </div>

    <!-- Step 3: Done -->
    <div class="setup-step" id="step-3">
      <div class="setup-title">&#10003; Setup Complete</div>
      <div class="setup-body">
        FormFlow is running. Share this address with other workstations in your lab:
      </div>
      <div class="lan-box" id="lan-box">Loading&hellip;</div>
      <a class="setup-btn" href="/">Open FormFlow &rarr;</a>
    </div>
  </div>
</div>

<script>
  function goStep(n) {
    document.querySelectorAll('.setup-step').forEach(el => el.classList.remove('active'));
    document.getElementById('step-' + n).classList.add('active');
    if (n === 3) loadLanIp();
  }

  // File picker / drag-drop wiring
  const dropZone = document.getElementById('drop-zone');
  const fileInput = document.getElementById('file-input');
  const installBtn = document.getElementById('install-btn');
  const dropLabel = document.getElementById('drop-label');
  let selectedFile = null;

  dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('over'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('over'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('over');
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  });
  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) setFile(fileInput.files[0]);
  });

  function setFile(f) {
    selectedFile = f;
    dropLabel.textContent = f.name;
    dropZone.classList.add('has-file');
    installBtn.disabled = false;
  }

  function showStatus(msg, type) {
    const el = document.getElementById('status-msg');
    el.textContent = msg;
    el.className = 'status-msg ' + type;
    el.style.display = 'block';
  }

  async function installZip() {
    if (!selectedFile) return;
    installBtn.disabled = true;
    showStatus('', 'info');
    const el = document.getElementById('status-msg');
    el.innerHTML = '<span class="spinner"></span>Uploading and installing PreFormServer&hellip;';
    el.className = 'status-msg info';
    el.style.display = 'block';

    const form = new FormData();
    form.append('archive', selectedFile);

    try {
      const resp = await fetch('/api/preform-setup/install-from-zip', { method: 'POST', body: form });
      const data = await resp.json();

      if (!resp.ok) {
        const code = data?.detail || '';
        if (code.includes('bad_zip')) {
          showStatus("That file doesn't look like a valid PreFormServer ZIP. Please download it from Formlabs.", 'error');
        } else if (code.includes('incompatible_version')) {
          const ver = data?.status?.detected_version || '?';
          const min = data?.status?.expected_version_min || '?';
          showStatus(`PreFormServer v${ver} is not supported. Minimum required: v${min}.`, 'error');
        } else {
          showStatus('Installation failed. Please try again or contact support.', 'error');
        }
        installBtn.disabled = false;
        return;
      }

      // Poll until ready
      await pollUntilReady();
    } catch (err) {
      showStatus('Network error. Please try again.', 'error');
      installBtn.disabled = false;
    }
  }

  async function pollUntilReady() {
    const el = document.getElementById('status-msg');
    for (let i = 0; i < 40; i++) {
      await new Promise(r => setTimeout(r, 1000));
      try {
        const resp = await fetch('/api/preform-setup/status');
        const data = await resp.json();
        if (data.readiness === 'ready') {
          showStatus(`PreFormServer v${data.detected_version} installed successfully.`, 'ok');
          setTimeout(() => goStep(3), 800);
          return;
        }
        if (data.readiness === 'incompatible_version') {
          const ver = data.detected_version || '?';
          const min = data.expected_version_min || '?';
          showStatus(`PreFormServer v${ver} is not supported. Minimum required: v${min}.`, 'error');
          document.getElementById('install-btn').disabled = false;
          return;
        }
      } catch (_) { /* retry */ }
    }
    showStatus('Timed out waiting for PreFormServer to start. Please try again.', 'error');
    document.getElementById('install-btn').disabled = false;
  }

  async function loadLanIp() {
    try {
      const resp = await fetch('/api/setup/lan-ip');
      const data = await resp.json();
      document.getElementById('lan-box').textContent = `http://${data.lan_ip}:${data.port}`;
    } catch (_) {
      document.getElementById('lan-box').textContent = 'http://localhost:8090';
    }
  }
</script>
</body>
</html>
```

- [ ] **Step 2: Verify page renders (dev server)**

```bash
uvicorn app.main:app --port 8090 --reload
```

Open `http://localhost:8090/setup` — confirm 3-step wizard renders. Confirm `http://localhost:8090/setup` redirects to `/` after manually setting readiness to `"ready"` in the DB.

- [ ] **Step 3: Commit**

```bash
git add app/static/setup.html
git commit -m "feat: add browser-based setup wizard HTML"
```

---

## Task 6: `run_tray.py` — EXE Entry Point

**Files:**
- Create: `run_tray.py`

This is the entry point PyInstaller will use. It must set env vars before importing the app, detect LAN IP, start uvicorn in a daemon thread, wait for the server to become healthy, open the browser, and run the pystray tray loop.

- [ ] **Step 1: Create `run_tray.py`**

```python
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _appdata_dir() -> Path:
    base = os.environ.get("APPDATA") or Path.home()
    return Path(base) / "FormFlow"


def _get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _configure_env() -> None:
    appdata = _appdata_dir()
    data_dir = appdata / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "uploads").mkdir(exist_ok=True)
    (data_dir / "screenshots").mkdir(exist_ok=True)
    (appdata / "logs").mkdir(exist_ok=True)

    os.environ.setdefault("FORMFLOW_WEB_HOST", "0.0.0.0")
    os.environ.setdefault("FORMFLOW_WEB_PORT", "8090")
    os.environ.setdefault("FORMFLOW_WEB_DATA_DIR", str(data_dir))
    os.environ.setdefault("FORMFLOW_WEB_DATABASE_PATH", str(data_dir / "formflow.db"))
    os.environ.setdefault("FORMFLOW_WEB_PRINT_DISPATCH_MODE", "real")


def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _start_uvicorn(port: int) -> None:
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="warning")


def _get_initial_url(port: int) -> str:
    from app.config import get_settings
    from app.database import load_preform_setup_state
    settings = get_settings()
    state = load_preform_setup_state(settings)
    if state.get("readiness") == "ready":
        return f"http://localhost:{port}/"
    return f"http://localhost:{port}/setup"


def _check_for_update(current_version: str) -> tuple[str, str] | None:
    """Returns (new_version, download_url) or None."""
    import urllib.request
    import json
    try:
        url = "https://api.github.com/repos/Harwav/FormFlow_Releases/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "FormFlow-Updater"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        tag = data.get("tag_name", "").lstrip("v")
        if not tag:
            return None
        from app.version import __version__
        if tuple(int(x) for x in tag.split(".")) > tuple(int(x) for x in __version__.split(".")):
            assets = data.get("assets", [])
            for asset in assets:
                if asset["name"].endswith(".exe") and "FormFlow" in asset["name"]:
                    return tag, asset["browser_download_url"]
    except Exception:
        pass
    return None


def _download_update(url: str, dest: Path) -> bool:
    import urllib.request
    try:
        urllib.request.urlretrieve(url, str(dest))
        return True
    except Exception:
        return False


def _launch_updater(current_pid: int, src: Path, dst: Path) -> None:
    """Extract bundled FormFlow_Updater.exe from PyInstaller bundle and launch it."""
    import subprocess
    import shutil

    # When frozen, sys._MEIPASS is the temp extraction dir
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is None:
        # Dev mode: just call the script directly
        updater_script = Path(__file__).parent / "scripts" / "updater.py"
        subprocess.Popen(
            [sys.executable, str(updater_script),
             "--pid", str(current_pid), "--src", str(src), "--dst", str(dst)],
            creationflags=0x00000008,  # DETACHED_PROCESS
        )
        return

    bundled = Path(meipass) / "FormFlow_Updater.exe"
    updater_dest = src.parent / "FormFlow_Updater.exe"
    shutil.copy2(str(bundled), str(updater_dest))
    subprocess.Popen(
        [str(updater_dest),
         "--pid", str(current_pid), "--src", str(src), "--dst", str(dst)],
        creationflags=0x00000008,
    )


def main() -> None:
    _configure_env()

    from app.version import __version__
    lan_ip = _get_lan_ip()
    port = int(os.environ.get("FORMFLOW_WEB_PORT", "8090"))

    # Start uvicorn in background daemon thread
    server_thread = threading.Thread(target=_start_uvicorn, args=(port,), daemon=True)
    server_thread.start()

    # Wait until server accepts connections
    if not _wait_for_server(port):
        # fallback: keep going, browser will show connection error
        pass

    # Set lan_ip on app state (import after uvicorn has initialised the module)
    try:
        from app.main import app as fastapi_app
        fastapi_app.state.lan_ip = lan_ip
    except Exception:
        pass

    initial_url = _get_initial_url(port)
    webbrowser.open(initial_url)

    # Build tray icon
    from PIL import Image
    import pystray

    # Load icon: try bundled path first, then local dev path
    icon_candidates = [
        Path(getattr(sys, "_MEIPASS", ".")) / "app" / "static" / "tray_icon.png",
        Path(__file__).parent / "app" / "static" / "tray_icon.png",
    ]
    icon_image = None
    for candidate in icon_candidates:
        if candidate.exists():
            icon_image = Image.open(str(candidate))
            break
    if icon_image is None:
        icon_image = Image.new("RGBA", (64, 64), (12, 141, 58, 255))

    update_info: list[tuple[str, str]] = []  # [(version, url)] when update available

    def open_app(icon, item):
        webbrowser.open(f"http://localhost:{port}/")

    def check_for_updates(icon, item):
        result = _check_for_update(__version__)
        if result is None:
            # No update — show notification via tray (pystray doesn't support balloons directly;
            # use ctypes MessageBox as fallback)
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, "FormFlow is up to date.", "Check for Updates", 0x40
            )
            return
        new_ver, dl_url = result
        import ctypes
        answer = ctypes.windll.user32.MessageBoxW(
            0,
            f"FormFlow v{new_ver} is available.\n\nUpdate now and restart?",
            "Update Available",
            0x04 | 0x40,  # MB_YESNO | MB_ICONINFORMATION
        )
        if answer != 6:  # IDYES == 6
            return
        import tempfile
        tmp = Path(tempfile.gettempdir()) / "formflow_update.exe"
        if not _download_update(dl_url, tmp):
            ctypes.windll.user32.MessageBoxW(0, "Download failed. Please try again.", "Update Error", 0x10)
            return
        current_exe = Path(sys.executable)
        _launch_updater(os.getpid(), tmp, current_exe)
        icon.stop()
        sys.exit(0)

    def quit_app(icon, item):
        icon.stop()
        sys.exit(0)

    lan_label = pystray.MenuItem(
        f"LAN: http://{lan_ip}:{port}", lambda *_: None, enabled=False
    )
    version_label = pystray.MenuItem(
        f"Version: v{__version__}", lambda *_: None, enabled=False
    )
    menu = pystray.Menu(
        pystray.MenuItem("Open FormFlow", open_app, default=True),
        pystray.Menu.SEPARATOR,
        lan_label,
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Check for Updates", check_for_updates),
        version_label,
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app),
    )

    # Start background update check (non-blocking)
    def _bg_update_check():
        time.sleep(5)  # brief delay after startup
        result = _check_for_update(__version__)
        if result:
            import ctypes
            new_ver = result[0]
            ctypes.windll.user32.MessageBoxW(
                0,
                f"FormFlow v{new_ver} is available.\nClick 'Check for Updates' in the tray to install.",
                "Update Available",
                0x40,
            )
    threading.Thread(target=_bg_update_check, daemon=True).start()

    tray = pystray.Icon("FormFlow", icon_image, "FormFlow", menu)
    tray.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it runs in dev mode**

```bash
python run_tray.py
```

Expected: tray icon appears in system tray, browser opens to `http://localhost:8090/setup` (first run) or `/`. No crash.

- [ ] **Step 3: Commit**

```bash
git add run_tray.py
git commit -m "feat: add run_tray.py EXE entry point with tray, auto-browser, updater"
```

---

## Task 7: Updater Helper

**Files:**
- Create: `scripts/updater.py`

This script is compiled into a tiny `FormFlow_Updater.exe` by PyInstaller. It accepts `--pid`, `--src`, `--dst` arguments, waits for the main process to exit, copies the new EXE over the old one, and relaunches it.

- [ ] **Step 1: Create `scripts/updater.py`**

```python
"""
FormFlow self-updater.
Called by run_tray.py during update:
  FormFlow_Updater.exe --pid <pid> --src <new_exe> --dst <current_exe>
Waits for <pid> to exit, replaces <dst> with <src>, relaunches <dst>.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--src", required=True)
    parser.add_argument("--dst", required=True)
    args = parser.parse_args()

    import psutil

    # Wait for the main process to exit (up to 30 s)
    deadline = time.time() + 30
    while time.time() < deadline:
        if not psutil.pid_exists(args.pid):
            break
        time.sleep(0.3)

    try:
        shutil.copy2(args.src, args.dst)
    except Exception as e:
        print(f"[updater] copy failed: {e}", file=sys.stderr)
        sys.exit(1)

    subprocess.Popen([args.dst], creationflags=0x00000008)  # DETACHED_PROCESS
    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it parses args without crashing**

```bash
python scripts/updater.py --pid 99999 --src x.exe --dst y.exe
```

Expected: exits quickly (PID 99999 does not exist, copy of `x.exe` fails, exits with code 1). That's correct — in production `src` will be a real downloaded file.

- [ ] **Step 3: Commit**

```bash
git add scripts/updater.py
git commit -m "feat: add updater helper script"
```

---

## Task 8: Windows Version Info

**Files:**
- Create: `version_info.txt`

This makes the EXE show proper metadata in Windows Explorer and looks legitimate to antivirus scanners.

- [ ] **Step 1: Create `version_info.txt`**

```
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(u'040904B0', [
        StringStruct(u'CompanyName', u'Harwav'),
        StringStruct(u'FileDescription', u'FormFlow Server'),
        StringStruct(u'FileVersion', u'1.0.0.0'),
        StringStruct(u'InternalName', u'formflow'),
        StringStruct(u'LegalCopyright', u'Harwav'),
        StringStruct(u'OriginalFilename', u'FormFlow_v1.0.0.exe'),
        StringStruct(u'ProductName', u'FormFlow'),
        StringStruct(u'ProductVersion', u'1.0.0.0'),
      ])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
```

- [ ] **Step 2: Commit**

```bash
git add version_info.txt
git commit -m "feat: add Windows EXE version info"
```

---

## Task 9: PyInstaller Specs

**Files:**
- Create: `formflow.spec`
- Create: `formflow_updater.spec`

- [ ] **Step 1: Create `formflow_updater.spec`**

```python
# formflow_updater.spec
from PyInstaller.building.build_main import Analysis, PYZ, EXE

a = Analysis(
    ['scripts/updater.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=['psutil'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FormFlow_Updater',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

- [ ] **Step 2: Create `formflow.spec`**

```python
# formflow.spec
import re
from pathlib import Path
from PyInstaller.building.build_main import Analysis, PYZ, EXE

version_text = Path('app/version.py').read_text()
version = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', version_text).group(1)

a = Analysis(
    ['run_tray.py'],
    pathex=['.'],
    binaries=[
        ('FormFlow_Updater.exe', '.'),  # bundled updater, built first
    ],
    datas=[
        ('app/static', 'app/static'),
    ],
    hiddenimports=[
        'uvicorn.lifespan.on',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.http.auto',
        'anyio._backends._asyncio',
        'pystray._win32',
        'PIL._imagingtk',
        'app.routers.setup',
        'app.routers.uploads',
        'app.routers.metrics',
        'app.routers.preform_setup',
        'app.routers.print_queue',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=f'FormFlow_v{version}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=None,
)
```

- [ ] **Step 3: Commit**

```bash
git add formflow.spec formflow_updater.spec
git commit -m "feat: add PyInstaller specs for main EXE and updater"
```

---

## Task 10: Build Script

**Files:**
- Create: `scripts/builders/build_deployment.py`
- Create: `scripts/builders/__init__.py` (empty)

- [ ] **Step 1: Create `scripts/builders/__init__.py`**

```python
```

(empty file)

- [ ] **Step 2: Create `scripts/builders/build_deployment.py`**

```python
"""
Build FormFlow Windows EXE.

Usage:
    python scripts/builders/build_deployment.py [--version X.Y.Z]

If --version is not passed, uses the current version in app/version.py.
Updates version_info.txt with the new version, then runs PyInstaller for
the updater spec first, then the main spec.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERSION_FILE = REPO_ROOT / "app" / "version.py"
VERSION_INFO_FILE = REPO_ROOT / "version_info.txt"


def read_version() -> str:
    text = VERSION_FILE.read_text()
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    if not m:
        raise ValueError("Could not find __version__ in app/version.py")
    return m.group(1)


def write_version(version: str) -> None:
    VERSION_FILE.write_text(f'__version__ = "{version}"\n')


def update_version_info(version: str) -> None:
    parts = version.split(".")
    while len(parts) < 4:
        parts.append("0")
    tuple_str = ", ".join(parts[:4])
    text = VERSION_INFO_FILE.read_text()
    text = re.sub(r"filevers=\([^)]+\)", f"filevers=({tuple_str})", text)
    text = re.sub(r"prodvers=\([^)]+\)", f"prodvers=({tuple_str})", text)
    dot_str = ".".join(parts[:4])
    text = re.sub(r"'FileVersion',\s*u'[^']*'", f"'FileVersion', u'{dot_str}'", text)
    text = re.sub(r"'ProductVersion',\s*u'[^']*'", f"'ProductVersion', u'{dot_str}'", text)
    text = re.sub(
        r"'OriginalFilename',\s*u'[^']*'",
        f"'OriginalFilename', u'FormFlow_v{version}.exe'",
        text,
    )
    VERSION_INFO_FILE.write_text(text)


def run(cmd: list[str]) -> None:
    print(f"[build] {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=None, help="Version to build (default: current)")
    args = parser.parse_args()

    version = args.version or read_version()
    print(f"[build] Building FormFlow v{version}")

    write_version(version)
    update_version_info(version)

    # 1. Build updater EXE first (needed as a binary input to main spec)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "formflow_updater.spec"])

    # Move updater EXE to repo root so main spec can find it
    updater_src = REPO_ROOT / "dist" / "FormFlow_Updater.exe"
    updater_dst = REPO_ROOT / "FormFlow_Updater.exe"
    if updater_src.exists():
        import shutil
        shutil.copy2(str(updater_src), str(updater_dst))

    # 2. Build main EXE
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "formflow.spec"])

    exe_path = REPO_ROOT / "dist" / f"FormFlow_v{version}.exe"
    if not exe_path.exists():
        print(f"[build] ERROR: expected EXE not found at {exe_path}", file=sys.stderr)
        sys.exit(1)

    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"[build] Built: {exe_path} ({size_mb:.1f} MB)")
    if size_mb < 40:
        print(f"[build] WARNING: EXE is suspiciously small ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify script runs without crashing (dry-run)**

```bash
python scripts/builders/build_deployment.py --version 1.0.0
```

Expected: prints build steps, runs PyInstaller, produces `dist/FormFlow_v1.0.0.exe` (40+ MB). This will take 1-3 minutes.

- [ ] **Step 4: Commit**

```bash
git add scripts/builders/__init__.py scripts/builders/build_deployment.py
git commit -m "feat: add deployment build script"
```

---

## Task 11: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/build-windows.yml`

- [ ] **Step 1: Create `.github/workflows/build-windows.yml`**

```yaml
name: Build Windows EXE

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:
    inputs:
      create_release:
        description: 'Create GitHub Release'
        required: false
        default: 'false'

jobs:
  build:
    runs-on: windows-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Build EXE
        run: python scripts/builders/build_deployment.py

      - name: Extract version
        id: version
        shell: bash
        run: |
          VERSION=$(python -c "from app.version import __version__; print(__version__)")
          echo "version=$VERSION" >> $GITHUB_OUTPUT

      - name: Verify EXE
        shell: bash
        run: |
          EXE="dist/FormFlow_v${{ steps.version.outputs.version }}.exe"
          if [ ! -f "$EXE" ]; then
            echo "ERROR: EXE not found at $EXE"
            exit 1
          fi
          SIZE=$(stat -c%s "$EXE" 2>/dev/null || stat -f%z "$EXE")
          echo "EXE size: $SIZE bytes"
          if [ "$SIZE" -lt 41943040 ]; then
            echo "ERROR: EXE is too small ($SIZE bytes)"
            exit 1
          fi

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: FormFlow_v${{ steps.version.outputs.version }}
          path: dist/FormFlow_v${{ steps.version.outputs.version }}.exe

      - name: Create GitHub Release
        if: startsWith(github.ref, 'refs/tags/v') || github.event.inputs.create_release == 'true'
        uses: softprops/action-gh-release@v2
        with:
          repository: Harwav/FormFlow_Releases
          tag_name: v${{ steps.version.outputs.version }}
          name: FormFlow v${{ steps.version.outputs.version }}
          files: dist/FormFlow_v${{ steps.version.outputs.version }}.exe
          token: ${{ secrets.RELEASES_REPO_TOKEN }}
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/build-windows.yml
git commit -m "feat: add GitHub Actions workflow for Windows EXE build and release"
```

---

## Task 12: End-to-End Verification

- [ ] **Step 1: Run full test suite**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q
```

Expected: all tests pass, including the new `test_setup_router.py`.

- [ ] **Step 2: Dev smoke test — run_tray.py**

```bash
python run_tray.py
```

Expected:
- Tray icon appears (green circle)
- Browser opens to `http://localhost:8090/setup` (first run) or `/`
- Wizard step 1 renders with correct styles
- After dropping a valid PreFormServer ZIP and clicking Install, wizard advances to step 3
- Step 3 shows LAN IP from `/api/setup/lan-ip`
- "Open FormFlow →" navigates to `/`
- Tray menu shows correct LAN address and version
- Quit exits cleanly

- [ ] **Step 3: PyInstaller build smoke test**

```bash
python scripts/builders/build_deployment.py --version 1.0.0
```

Expected:
- `dist/FormFlow_v1.0.0.exe` exists and is > 40 MB
- Double-click the EXE: tray icon appears, browser opens, wizard works

- [ ] **Step 4: LAN access test**

From a second machine on the same network, browse to `http://<server-LAN-IP>:8090`. Expected: FormFlow app loads.

- [ ] **Step 5: Update flow test**

Temporarily set `__version__ = "0.0.1"` in `app/version.py`, rebuild the EXE, and launch it. Expected: update notification appears on startup. Restore version after testing.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat: complete Windows EXE deployment — tray, setup wizard, auto-updater, CI pipeline"
```
