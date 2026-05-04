# Windows EXE Deployment — Revised Bulletproof Plan (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Supersedes:** [2026-04-29-windows-exe-deployment.md](2026-04-29-windows-exe-deployment.md)

## Context

Replaces `docs/superpowers/plans/2026-04-29-windows-exe-deployment.md`. The original plan had 3 BLOCKERs (wrong form field name, broken test fixture pattern, threading import race) and missing tasks for logging, single-instance lock, splash screen, and several PyInstaller correctness items. This revision fixes all of those and folds in the user's explicit decisions:

- **LAN binding:** trust-the-LAN, no auth — but only after wizard completes (loopback during setup), and the wizard explicitly warns about patient-data exposure.
- **Code signing:** ship unsigned for v1; document SmartScreen workaround in wizard step 1.
- **Observability:** rotating file logs in `%APPDATA%/Andent Web/logs/`, "View Logs" tray menu item, no remote telemetry.
- **Packaging:** PyInstaller `--onefile` with `--splash` so users see something within 200ms of double-click.

Goal unchanged: a non-technical dental lab tech downloads one `.exe`, double-clicks, and is fully running within minutes.

---

## Verified facts (pre-flight)

- Form upload field is **`package`**, not `archive` ([app/routers/preform_setup.py:336](../../../app/routers/preform_setup.py#L336))
- Existing test fixture pattern is `build_settings(data_dir=...)` + `create_app(settings)` ([tests/test_preform_setup.py:21-31](../../../tests/test_preform_setup.py#L21-L31)) — NOT `monkeypatch.setenv`
- `app/config.py` defaults `server_host="127.0.0.1"`; `get_settings()` is `@lru_cache(maxsize=1)` so env vars must be set **before** first call
- `.omx/preform-list-materials-latest.json` is read at runtime ([app/routers/preform_setup.py:89](../../../app/routers/preform_setup.py#L89)) — must be bundled in `datas`
- `app/main.py` does not currently set `app.state.lan_ip` — fresh field
- Existing CSS variables (`--accent`, `--clear`, `--font-display`, etc.) all exist in styles.css and are safe to reuse

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ Andent_Web_v1.0.0.exe (PyInstaller --onefile)       │
│                                                     │
│  splash.png ──> bootstrap (10ms)                    │
│       │                                             │
│       ▼                                             │
│  run_tray.py main()                                 │
│       ├─ acquire single-instance mutex              │
│       ├─ configure logging → %APPDATA%/logs         │
│       ├─ resolve LAN IP, set ANDENT_WEB_LAN_IP env  │
│       ├─ start uvicorn (127.0.0.1 until ready;      │
│       │    flips to 0.0.0.0 after wizard done)      │
│       ├─ wait for /health/live                      │
│       ├─ open browser → /setup or /                 │
│       ├─ pystray.Icon.run() (blocks main thread)    │
│       └─ on Quit: terminate uvicorn, release mutex  │
│                                                     │
│  bundled: Andent_Updater.exe (in _MEIPASS)          │
│  bundled: app/static/, .omx/, splash.png            │
└─────────────────────────────────────────────────────┘
```

**Update flow:** Tray "Check for Updates" → GitHub API (cached 24h on disk) → confirm dialog → download new EXE to `%TEMP%` → copy `Andent_Updater.exe` from `_MEIPASS` to `%TEMP%` → launch updater detached → main exits → updater waits for PID → 3× retry copy → relaunch.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/version.py` | Create | Single source of truth for `__version__` |
| `app/logging_config.py` | Create | Rotating file handler + log dir resolver |
| `app/state.py` | Create | Module-level `LAN_IP` + `WIZARD_COMPLETED` flags |
| `app/routers/setup.py` | Create | `GET /setup`, `GET /api/setup/lan-ip`, `POST /api/setup/complete` |
| `app/static/setup.html` | Create | 4-step wizard (welcome+SmartScreen note → install → LAN-confirm → done) |
| `app/static/tray_icon.png` | Create | 64×64 brand icon |
| `app/static/splash.png` | Create | 480×320 splash for PyInstaller |
| `app/main.py` | Modify | Register setup router; read LAN IP + wizard state from `app.state` |
| `app/config.py` | Modify | Add `lan_bind_after_setup` setting (default True) |
| `requirements.txt` | Modify | Pin pystray, Pillow, psutil, pyinstaller |
| `run_tray.py` | Create | EXE entry: mutex, logging, env, uvicorn, splash close, tray, updater |
| `scripts/updater.py` | Create | Wait-for-pid + retry copy + relaunch |
| `scripts/builders/build_deployment.py` | Create | Version bump → build updater → build main with splash |
| `andent_web.spec` | Create | PyInstaller spec (--onefile + splash + .omx + multipart) |
| `andent_updater.spec` | Create | Tiny updater spec (console=True for diag) |
| `version_info.txt` | Create + .gitignore | Generated per build, NOT committed |
| `.github/workflows/build-windows.yml` | Create | Tag push → build → release |
| `tests/test_setup_router.py` | Create | TDD coverage matching repo fixture pattern |
| `tests/test_run_tray_helpers.py` | Create | Unit tests for LAN IP detection, mutex, log dir |
| `.gitignore` | Modify | Add `version_info.txt`, `dist/`, `build/`, `*.spec.bak` |

---

## Task 1: Version + Logging + State Foundation

**Why bundled:** these three modules are imported by every later task; building them as a unit avoids three small commits.

**Files to create:** `app/version.py`, `app/logging_config.py`, `app/state.py`

- [ ] **Step 1: `app/version.py`**

```python
__version__ = "1.0.0"
```

- [ ] **Step 2: `app/state.py`** — module-level singletons that survive across `create_app()` calls in tests

```python
"""Module-level runtime state set by run_tray.py before uvicorn starts.

Read by app.main.create_app() to populate app.state without import-order races.
"""
from __future__ import annotations

LAN_IP: str = "127.0.0.1"
WIZARD_COMPLETED: bool = False
LAN_BIND_ALLOWED: bool = False
```

- [ ] **Step 3: `app/logging_config.py`**

```python
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def appdata_log_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    log_dir = Path(base) / "Andent Web" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def configure_logging(level: int = logging.INFO) -> Path:
    log_path = appdata_log_dir() / "andent_web.log"
    handler = RotatingFileHandler(
        str(log_path), maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    # Don't double-add if Python is re-running this (PyInstaller respawn)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(level)
    # Quiet uvicorn access spam in file
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    return log_path
```

- [ ] **Step 4: Tests** — `tests/test_run_tray_helpers.py` (TDD scaffold; more tests added in Task 6)

```python
from __future__ import annotations

import logging
from pathlib import Path

from app.logging_config import appdata_log_dir, configure_logging


def test_appdata_log_dir_is_created(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    result = appdata_log_dir()
    assert result == tmp_path / "Andent Web" / "logs"
    assert result.is_dir()


def test_configure_logging_creates_log_file(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    log_path = configure_logging(level=logging.DEBUG)
    logging.info("smoke")
    for h in logging.getLogger().handlers:
        h.flush()
    assert log_path.exists()
    assert "smoke" in log_path.read_text(encoding="utf-8")
```

- [ ] **Step 5: Run tests + commit**

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"; python -m pytest tests/test_run_tray_helpers.py -v
git add app/version.py app/logging_config.py app/state.py tests/test_run_tray_helpers.py
git commit -m "feat: add version, state, and logging foundation"
```

---

## Task 2: Dependencies

**Files:** `requirements.txt`

- [ ] **Step 1: Append to `requirements.txt`** (do not rewrite — preserve existing pins)

```
# Desktop packaging (Windows EXE)
pystray==0.19.5
Pillow==10.4.0
psutil==6.1.1
pyinstaller==6.11.1
```

- [ ] **Step 2: Install + verify**

```powershell
pip install pystray==0.19.5 Pillow==10.4.0 psutil==6.1.1 pyinstaller==6.11.1
python -c "import pystray, PIL, psutil, PyInstaller; print('ok')"
```

- [ ] **Step 3: Commit**

```powershell
git add requirements.txt
git commit -m "feat: add Windows packaging dependencies"
```

---

## Task 3: Static Assets (icon + splash)

**Files:** `app/static/tray_icon.png`, `app/static/splash.png`

- [ ] **Step 1: Generate both with one Python snippet**

```python
from PIL import Image, ImageDraw, ImageFont

# Tray icon: 64x64 green circle (matches --clear in styles.css)
icon = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
ImageDraw.Draw(icon).ellipse([4, 4, 60, 60], fill=(12, 141, 58, 255))
icon.save("app/static/tray_icon.png")

# Splash: 480x320 with brand text on cream background
splash = Image.new("RGB", (480, 320), (254, 253, 249))  # --bg
draw = ImageDraw.Draw(splash)
draw.ellipse([200, 80, 280, 160], fill=(255, 90, 0))  # --accent dot
try:
    font = ImageFont.truetype("arial.ttf", 36)
except OSError:
    font = ImageFont.load_default()
draw.text((240, 200), "Andent Web", fill=(17, 17, 16), font=font, anchor="mm")
draw.text((240, 250), "Starting…", fill=(112, 110, 107), font=font, anchor="mm")
splash.save("app/static/splash.png")
```

- [ ] **Step 2: Verify**

```powershell
python -c "from PIL import Image; print(Image.open('app/static/tray_icon.png').size, Image.open('app/static/splash.png').size)"
```
Expected: `(64, 64) (480, 320)`

- [ ] **Step 3: Commit**

```powershell
git add app/static/tray_icon.png app/static/splash.png
git commit -m "feat: add tray icon and splash screen assets"
```

---

## Task 4: Setup Router (TDD, fixture pattern matches repo)

**Files:** `app/routers/setup.py`, `tests/test_setup_router.py`, `app/main.py` (modify)

The router serves `/setup` (HTML), `/api/setup/lan-ip` (JSON), and `POST /api/setup/complete` (flips wizard-done flag → flips bind from loopback to 0.0.0.0 on next start).

- [ ] **Step 1: Write failing tests using existing repo fixture pattern**

```python
# tests/test_setup_router.py
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import build_settings
from app.database import init_db, save_preform_setup_state
from app.main import create_app
from app import state as runtime_state


def _build(tmp_path: Path):
    settings = build_settings(
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "andent_web.db",
    )
    init_db(settings)
    return settings


@pytest.fixture()
def client(tmp_path):
    settings = _build(tmp_path)
    app = create_app(settings)
    app.state.lan_ip = "192.168.1.100"
    with TestClient(app, follow_redirects=False) as c:
        yield c, settings
    runtime_state.WIZARD_COMPLETED = False  # reset module state


def test_lan_ip_endpoint_returns_json(client):
    c, _ = client
    resp = c.get("/api/setup/lan-ip")
    assert resp.status_code == 200
    data = resp.json()
    assert data["lan_ip"] == "192.168.1.100"
    assert data["port"] == 8090


def test_setup_page_redirects_when_ready(client):
    c, settings = client
    save_preform_setup_state(settings, readiness="ready")
    runtime_state.WIZARD_COMPLETED = True
    resp = c.get("/setup")
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"


def test_setup_page_serves_html_when_not_installed(client):
    c, _ = client
    resp = c.get("/setup")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert b"setup" in resp.content.lower()


def test_complete_marks_wizard_done(client):
    c, _ = client
    assert runtime_state.WIZARD_COMPLETED is False
    resp = c.post("/api/setup/complete", json={"allow_lan": True})
    assert resp.status_code == 200
    assert runtime_state.WIZARD_COMPLETED is True
    assert runtime_state.LAN_BIND_ALLOWED is True
```

- [ ] **Step 2: Verify tests fail with import error**

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"; python -m pytest tests/test_setup_router.py -v
```

- [ ] **Step 3: Create `app/routers/setup.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from .. import state as runtime_state
from ..database import load_preform_setup_state

router = APIRouter()


class CompletePayload(BaseModel):
    allow_lan: bool = True


@router.get("/setup", include_in_schema=False)
async def setup_page(request: Request):
    settings = request.app.state.settings
    state = load_preform_setup_state(settings)
    if state.get("readiness") == "ready" and runtime_state.WIZARD_COMPLETED:
        return RedirectResponse(url="/", status_code=302)
    return FileResponse(settings.static_dir / "setup.html")


@router.get("/api/setup/lan-ip")
async def lan_ip(request: Request) -> dict:
    return {
        "lan_ip": getattr(request.app.state, "lan_ip", runtime_state.LAN_IP),
        "port": request.app.state.settings.server_port,
    }


@router.post("/api/setup/complete")
async def complete(payload: CompletePayload | None = None) -> dict:
    runtime_state.WIZARD_COMPLETED = True
    runtime_state.LAN_BIND_ALLOWED = bool(payload.allow_lan) if payload else True
    return {"ok": True, "wizard_completed": True, "lan_allowed": runtime_state.LAN_BIND_ALLOWED}
```

- [ ] **Step 4: Modify `app/main.py`** — register router + populate `app.state.lan_ip` from `app.state` module

After existing imports add:
```python
from . import state as runtime_state
from .routers.setup import router as setup_router
```

Inside `create_app()`, after the existing `app.state.default_print_dispatch_mode = ...` line:
```python
    app.state.lan_ip = runtime_state.LAN_IP
```

After the last `app.include_router(...)` line:
```python
    app.include_router(setup_router)
```

- [ ] **Step 5: Run tests + full suite for regressions**

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"; python -m pytest tests/test_setup_router.py -v
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"; python -m pytest tests/ -q
```

- [ ] **Step 6: Commit**

```powershell
git add app/routers/setup.py app/main.py tests/test_setup_router.py
git commit -m "feat: add setup router with wizard, lan-ip, and completion endpoints"
```

---

## Task 5: Setup Wizard HTML (4 steps)

**Files:** `app/static/setup.html`

Four steps now: (1) Welcome **with SmartScreen explainer**, (2) Install PreFormServer, (3) LAN exposure confirm, (4) Done.

Critical fixes from original:
- Form field is `package` not `archive`
- Step 3 is new — explicit "anyone on this network can read patient files" warning before flipping bind
- Calls `POST /api/setup/complete` to set the wizard-done flag

- [ ] **Step 1: Create `app/static/setup.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Andent Web — Setup</title>
  <link rel="stylesheet" href="/static/styles.css" />
  <style>
    .setup-shell {
      min-height: 100vh; display: flex;
      align-items: center; justify-content: center;
      background: var(--bg);
    }
    .setup-card {
      background: var(--surface); border: 1px solid var(--line);
      border-radius: 12px; box-shadow: var(--shadow);
      padding: 48px 56px; width: 100%; max-width: 520px;
    }
    .setup-logo {
      font-family: var(--font-display); font-size: 1.6rem;
      font-weight: 700; color: var(--ink); margin-bottom: 8px;
    }
    .setup-step { display: none; }
    .setup-step.active { display: block; }
    .setup-title {
      font-family: var(--font-display); font-size: 1.4rem;
      font-weight: 600; margin: 24px 0 8px;
    }
    .setup-body {
      color: var(--muted); font-size: 0.95rem;
      line-height: 1.6; margin-bottom: 28px;
    }
    .setup-btn {
      display: inline-block; background: var(--accent); color: #fff;
      border: none; border-radius: 8px; padding: 12px 28px;
      font-size: 1rem; font-family: var(--font-ui);
      cursor: pointer; text-decoration: none;
    }
    .setup-btn:hover { background: var(--accent-dark); }
    .setup-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .drop-zone {
      border: 2px dashed var(--line); border-radius: 8px;
      padding: 36px 24px; text-align: center; color: var(--muted);
      cursor: pointer; margin-bottom: 20px;
      transition: border-color 0.15s, background 0.15s;
    }
    .drop-zone.over { border-color: var(--accent); background: var(--accent-soft); }
    .drop-zone.has-file { border-color: var(--clear); background: var(--clear-soft); color: var(--clear); }
    .status-msg { margin-top: 16px; padding: 12px 16px; border-radius: 6px; font-size: 0.9rem; }
    .status-msg.error { background: var(--danger-soft); color: var(--danger); }
    .status-msg.info  { background: var(--info-soft);   color: var(--info); }
    .status-msg.ok    { background: var(--clear-soft);  color: var(--clear); }
    .lan-box {
      background: var(--surface-soft); border: 1px solid var(--line);
      border-radius: 8px; padding: 16px 20px;
      font-family: monospace; font-size: 1rem;
      color: var(--info); margin: 16px 0 28px;
    }
    .smartscreen-note {
      background: var(--info-soft); color: var(--info);
      padding: 12px 16px; border-radius: 6px;
      font-size: 0.85rem; margin: 16px 0; line-height: 1.5;
    }
    .lan-warn {
      background: var(--danger-soft); color: var(--danger);
      padding: 14px 18px; border-radius: 6px;
      font-size: 0.9rem; margin: 16px 0; line-height: 1.5;
    }
    .lan-warn strong { display: block; margin-bottom: 4px; }
    .spinner {
      display: inline-block; width: 18px; height: 18px;
      border: 3px solid var(--line); border-top-color: var(--accent);
      border-radius: 50%; animation: spin 0.7s linear infinite;
      vertical-align: middle; margin-right: 8px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
<div class="setup-shell"><div class="setup-card">
  <div class="setup-logo">Andent Web</div>

  <!-- Step 1: Welcome + SmartScreen explainer -->
  <div class="setup-step active" id="step-1">
    <div class="setup-title">Welcome</div>
    <div class="setup-body">
      Andent Web manages your dental 3D print workflow. Before you begin,
      you'll need the <strong>PreFormServer ZIP</strong> from Formlabs.
      Download it from the Formlabs Dashboard, then click Get Started.
    </div>
    <div class="smartscreen-note">
      <strong>Note:</strong> Windows may have shown a "Windows protected your PC"
      warning when you opened Andent Web. This is normal for new applications.
      You safely clicked <em>More info → Run anyway</em> to get here.
    </div>
    <button class="setup-btn" onclick="goStep(2)">Get Started &rarr;</button>
  </div>

  <!-- Step 2: Install PreFormServer (form field = 'package') -->
  <div class="setup-step" id="step-2">
    <div class="setup-title">Install PreFormServer</div>
    <div class="setup-body">Drag and drop the PreFormServer ZIP here, or click to browse.</div>
    <div class="drop-zone" id="drop-zone" onclick="document.getElementById('file-input').click()">
      <span id="drop-label">Drop PreFormServer.zip here or click to browse</span>
      <input type="file" id="file-input" accept=".zip" style="display:none" />
    </div>
    <button class="setup-btn" id="install-btn" disabled onclick="installZip()">Install</button>
    <div id="status-msg" style="display:none" class="status-msg"></div>
  </div>

  <!-- Step 3: LAN exposure consent (NEW) -->
  <div class="setup-step" id="step-3">
    <div class="setup-title">Network Sharing</div>
    <div class="setup-body">
      Andent Web can be accessed from other workstations in your lab.
      Confirm you want to allow this:
    </div>
    <div class="lan-warn">
      <strong>Important — patient data exposure</strong>
      Anyone on this network will be able to view and modify
      uploaded case files. Only enable on a trusted lab network — never on hotel,
      conference, or guest Wi-Fi.
    </div>
    <button class="setup-btn" onclick="completeSetup(true)">Allow LAN Access</button>
    <button class="setup-btn" style="background:var(--muted);margin-left:12px"
            onclick="completeSetup(false)">Local Only</button>
  </div>

  <!-- Step 4: Done -->
  <div class="setup-step" id="step-4">
    <div class="setup-title">&#10003; Setup Complete</div>
    <div class="setup-body" id="done-msg">Andent Web is running.</div>
    <div class="lan-box" id="lan-box">Loading&hellip;</div>
    <a class="setup-btn" href="/">Open Andent Web &rarr;</a>
  </div>
</div></div>

<script>
  function goStep(n) {
    document.querySelectorAll('.setup-step').forEach(el => el.classList.remove('active'));
    document.getElementById('step-' + n).classList.add('active');
    if (n === 4) loadLanIp();
  }

  const dropZone = document.getElementById('drop-zone');
  const fileInput = document.getElementById('file-input');
  const installBtn = document.getElementById('install-btn');
  const dropLabel = document.getElementById('drop-label');
  let selectedFile = null;
  dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('over'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('over'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault(); dropZone.classList.remove('over');
    if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener('change', () => fileInput.files[0] && setFile(fileInput.files[0]));

  function setFile(f) {
    selectedFile = f; dropLabel.textContent = f.name;
    dropZone.classList.add('has-file'); installBtn.disabled = false;
  }
  function showStatus(msg, type) {
    const el = document.getElementById('status-msg');
    el.textContent = msg; el.className = 'status-msg ' + type; el.style.display = 'block';
  }

  async function installZip() {
    if (!selectedFile) return;
    installBtn.disabled = true;
    const el = document.getElementById('status-msg');
    el.innerHTML = '<span class="spinner"></span>Uploading and installing PreFormServer&hellip;';
    el.className = 'status-msg info'; el.style.display = 'block';

    const form = new FormData();
    form.append('package', selectedFile);  // FIXED: 'package' not 'archive'

    try {
      const resp = await fetch('/api/preform-setup/install-from-zip', { method: 'POST', body: form });
      const data = await resp.json();
      if (!resp.ok) {
        const code = data?.detail || '';
        if (code.includes('bad_zip')) {
          showStatus("That doesn't look like a valid PreFormServer ZIP. Please re-download from Formlabs.", 'error');
        } else if (code.includes('incompatible_version')) {
          showStatus(`PreFormServer version is not supported. ${code}`, 'error');
        } else {
          showStatus('Installation failed. Check the application logs in %APPDATA%\\Andent Web\\logs.', 'error');
        }
        installBtn.disabled = false; return;
      }
      await pollUntilReady();
    } catch (err) {
      showStatus('Network error. Please try again.', 'error');
      installBtn.disabled = false;
    }
  }

  async function pollUntilReady() {
    for (let i = 0; i < 40; i++) {
      await new Promise(r => setTimeout(r, 1000));
      try {
        const resp = await fetch('/api/preform-setup/status');
        const data = await resp.json();
        if (data.readiness === 'ready') {
          showStatus(`PreFormServer v${data.detected_version} installed.`, 'ok');
          setTimeout(() => goStep(3), 800); return;
        }
        if (data.readiness === 'incompatible_version') {
          showStatus(`PreFormServer v${data.detected_version} is not supported.`, 'error');
          installBtn.disabled = false; return;
        }
      } catch (_) { /* retry */ }
    }
    showStatus('Timed out waiting for PreFormServer to start.', 'error');
    installBtn.disabled = false;
  }

  async function completeSetup(allowLan) {
    try {
      await fetch('/api/setup/complete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({allow_lan: allowLan})
      });
      if (!allowLan) {
        document.getElementById('done-msg').textContent =
          'Andent Web is running on this computer only.';
      }
      goStep(4);
    } catch (_) { goStep(4); }
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

- [ ] **Step 2: Manual smoke test in dev**

```powershell
uvicorn app.main:app --port 8090 --reload
# Browse http://localhost:8090/setup — confirm 4 steps render
```

- [ ] **Step 3: Commit**

```powershell
git add app/static/setup.html
git commit -m "feat: add 4-step setup wizard with SmartScreen note and LAN consent"
```

---

## Task 6: `run_tray.py` — bulletproof entry point

**Files:** `run_tray.py`

Critical changes vs original:
- **Configures logging FIRST** (so any later crash is captured)
- **Acquires Windows named mutex** before doing anything else (single-instance lock)
- **Sets LAN IP via `app.state` module BEFORE uvicorn starts** — no thread race
- **No import of `app.main` from main thread after uvicorn started**
- **Splash screen close hook** for PyInstaller `--splash`
- **GitHub update check is cached to disk for 24h**
- **Updater is copied to `%TEMP%`, not next to the EXE** (handles Program Files case)
- **LAN IP detection prefers RFC1918 over the 8.8.8.8 trick** (handles VPN + air-gap)

- [ ] **Step 1: Create `run_tray.py`**

```python
"""Andent Web tray launcher — PyInstaller --onefile entry point."""
from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Splash close (no-op in dev mode)
try:
    import pyi_splash  # type: ignore
    _SPLASH = pyi_splash
except ImportError:
    _SPLASH = None


def _appdata_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Andent Web"


def _acquire_single_instance_mutex() -> object | None:
    """Return mutex handle if we're the only instance; None if another is running."""
    if os.name != "nt":
        return object()  # dev mode on non-Windows: no-op
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
    handle = kernel32.CreateMutexW(None, True, "Global\\AndentWebSingletonMutex")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


def _detect_lan_ip() -> str:
    """Prefer RFC1918 addresses over the 8.8.8.8 trick (handles VPN + air-gap)."""
    candidates: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            ip = info[4][0]
            if ip.startswith(("10.", "192.168.")) or ip.startswith("172."):
                candidates.append(ip)
    except Exception:
        pass
    rfc1918 = [
        ip for ip in candidates
        if ip.startswith("10.") or ip.startswith("192.168.")
        or (ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31)
    ]
    if rfc1918:
        rfc1918.sort(key=lambda x: (
            0 if x.startswith("192.168.") else 1 if x.startswith("10.") else 2
        ))
        return rfc1918[0]
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _configure_env(bind_lan: bool) -> None:
    appdata = _appdata_dir()
    data_dir = appdata / "data"
    for sub in (data_dir, data_dir / "uploads", data_dir / "screenshots", appdata / "logs"):
        sub.mkdir(parents=True, exist_ok=True)

    host = "0.0.0.0" if bind_lan else "127.0.0.1"
    os.environ.setdefault("ANDENT_WEB_HOST", host)
    os.environ.setdefault("ANDENT_WEB_PORT", "8090")
    os.environ.setdefault("ANDENT_WEB_DATA_DIR", str(data_dir))
    os.environ.setdefault("ANDENT_WEB_DATABASE_PATH", str(data_dir / "andent_web.db"))
    os.environ.setdefault("ANDENT_WEB_PRINT_DISPATCH_MODE", "real")


def _wizard_completed_marker() -> Path:
    return _appdata_dir() / "wizard_completed"


def _is_first_run() -> bool:
    return not _wizard_completed_marker().exists()


def _start_uvicorn(port: int, host: str) -> None:
    import uvicorn
    uvicorn.run("app.main:app", host=host, port=port, log_level="warning")


def _wait_for_server(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _initial_url(port: int) -> str:
    if _is_first_run():
        return f"http://localhost:{port}/setup"
    try:
        from app.config import get_settings
        from app.database import load_preform_setup_state
        state = load_preform_setup_state(get_settings())
        if state.get("readiness") == "ready":
            return f"http://localhost:{port}/"
    except Exception:
        logging.exception("Could not read setup state")
    return f"http://localhost:{port}/setup"


# --- Update check (cached 24h) ---

def _update_cache_path() -> Path:
    return _appdata_dir() / "update_check.json"


def _is_newer(remote: str, local: str) -> bool:
    try:
        def parts(v: str) -> tuple[int, ...]:
            return tuple(int(p) for p in v.split(".")[:3] if p.isdigit())
        return parts(remote) > parts(local)
    except Exception:
        return False


def _check_for_update(current_version: str) -> tuple[str, str] | None:
    import urllib.request
    try:
        url = "https://api.github.com/repos/Harwav/Andent_Releases/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "AndentWeb-Updater"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        tag = data.get("tag_name", "").lstrip("v")
        if not tag or not _is_newer(tag, current_version):
            return None
        for asset in data.get("assets", []):
            if asset["name"].endswith(".exe") and "Andent_Web" in asset["name"]:
                return tag, asset["browser_download_url"]
    except Exception:
        logging.exception("Update check failed")
    return None


def _check_for_update_cached(current_version: str) -> tuple[str, str] | None:
    cache = _update_cache_path()
    now = time.time()
    if cache.exists() and (now - cache.stat().st_mtime) < 86400:
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("new_version") and data.get("download_url"):
                if _is_newer(data["new_version"], current_version):
                    return data["new_version"], data["download_url"]
                return None
        except Exception:
            pass
    result = _check_for_update(current_version)
    cache.write_text(json.dumps({
        "checked_at": now,
        "new_version": result[0] if result else None,
        "download_url": result[1] if result else None,
    }), encoding="utf-8")
    return result


def _download_update(url: str, dest: Path) -> bool:
    import urllib.request
    try:
        urllib.request.urlretrieve(url, str(dest))
        return True
    except Exception:
        logging.exception("Update download failed")
        return False


def _launch_updater(current_pid: int, src: Path, dst: Path) -> None:
    import shutil
    import tempfile
    DETACHED = 0x00000008
    NO_WINDOW = 0x08000000
    flags = DETACHED | NO_WINDOW

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is None:
        updater_script = Path(__file__).parent / "scripts" / "updater.py"
        subprocess.Popen(
            [sys.executable, str(updater_script),
             "--pid", str(current_pid), "--src", str(src), "--dst", str(dst)],
            creationflags=flags,
        )
        return

    bundled = Path(meipass) / "Andent_Updater.exe"
    tmp_updater = Path(tempfile.gettempdir()) / "Andent_Updater.exe"
    shutil.copy2(str(bundled), str(tmp_updater))
    subprocess.Popen(
        [str(tmp_updater),
         "--pid", str(current_pid), "--src", str(src), "--dst", str(dst)],
        creationflags=flags,
    )


def main() -> None:
    # 1. Logging FIRST
    from app.logging_config import configure_logging
    log_path = configure_logging()
    logging.info("Andent Web starting (log: %s)", log_path)

    # 2. Single-instance check
    mutex = _acquire_single_instance_mutex()
    if mutex is None:
        logging.warning("Another Andent Web instance is already running. Exiting.")
        if _SPLASH:
            _SPLASH.close()
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, "Andent Web is already running. Check your system tray.",
                "Andent Web", 0x40,
            )
        sys.exit(0)

    # 3. Detect LAN, set runtime_state BEFORE uvicorn imports app
    lan_ip = _detect_lan_ip()
    bind_lan = not _is_first_run()
    _configure_env(bind_lan)
    logging.info("LAN IP=%s, bind_lan=%s", lan_ip, bind_lan)

    from app import state as runtime_state
    runtime_state.LAN_IP = lan_ip
    runtime_state.LAN_BIND_ALLOWED = bind_lan
    runtime_state.WIZARD_COMPLETED = not _is_first_run()

    from app.version import __version__

    # 4. Start uvicorn
    port = int(os.environ["ANDENT_WEB_PORT"])
    host = os.environ["ANDENT_WEB_HOST"]
    threading.Thread(
        target=_start_uvicorn, args=(port, host), daemon=True
    ).start()

    if not _wait_for_server(port, timeout=30.0):
        logging.error("Server did not start within 30s")
        if _SPLASH:
            _SPLASH.close()
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, f"Andent Web could not start. See logs:\n{log_path}",
                "Startup Error", 0x10,
            )
        sys.exit(1)

    # 5. Close splash, open browser
    if _SPLASH:
        _SPLASH.close()
    webbrowser.open(_initial_url(port))

    # 6. Watch for wizard completion → write marker so next launch flips bind to LAN
    def _watch_wizard_completion():
        marker = _wizard_completed_marker()
        while True:
            if runtime_state.WIZARD_COMPLETED and not marker.exists():
                marker.write_text("ok", encoding="utf-8")
                logging.info("Wizard marked complete; next start will honor LAN consent")
            time.sleep(2)
    threading.Thread(target=_watch_wizard_completion, daemon=True).start()

    # 7. Tray icon
    from PIL import Image
    import pystray

    icon_candidates = [
        Path(getattr(sys, "_MEIPASS", ".")) / "app" / "static" / "tray_icon.png",
        Path(__file__).parent / "app" / "static" / "tray_icon.png",
    ]
    icon_image = None
    for c in icon_candidates:
        if c.exists():
            icon_image = Image.open(str(c)); break
    if icon_image is None:
        icon_image = Image.new("RGBA", (64, 64), (12, 141, 58, 255))

    def open_app(icon, item): webbrowser.open(f"http://localhost:{port}/")
    def open_logs(icon, item): os.startfile(str(_appdata_dir() / "logs"))  # noqa
    def quit_app(icon, item):
        logging.info("Quit requested from tray")
        icon.stop(); sys.exit(0)

    def check_for_updates(icon, item):
        result = _check_for_update_cached(__version__)
        import ctypes
        if result is None:
            ctypes.windll.user32.MessageBoxW(0, "Andent Web is up to date.", "Check for Updates", 0x40)
            return
        new_ver, dl_url = result
        answer = ctypes.windll.user32.MessageBoxW(
            0, f"Andent Web v{new_ver} is available.\n\nUpdate now and restart?",
            "Update Available", 0x04 | 0x40,
        )
        if answer != 6:
            return
        import tempfile
        tmp = Path(tempfile.gettempdir()) / "andent_web_update.exe"
        if not _download_update(dl_url, tmp):
            ctypes.windll.user32.MessageBoxW(0, "Download failed.", "Update Error", 0x10)
            return
        _launch_updater(os.getpid(), tmp, Path(sys.executable))
        icon.stop(); sys.exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Open Andent Web", open_app, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"LAN: http://{lan_ip}:{port}" if bind_lan else "Local only",
                         lambda *_: None, enabled=False),
        pystray.MenuItem(f"Version: v{__version__}", lambda *_: None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Check for Updates", check_for_updates),
        pystray.MenuItem("View Logs", open_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app),
    )

    def _bg_check():
        time.sleep(5)
        result = _check_for_update_cached(__version__)
        if result:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, f"Andent Web v{result[0]} is available.\nUse the tray menu to install.",
                "Update Available", 0x40,
            )
    threading.Thread(target=_bg_check, daemon=True).start()

    pystray.Icon("Andent Web", icon_image, "Andent Web", menu).run()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        logging.exception("Fatal error in run_tray.py")
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, f"Andent Web crashed. Logs: {_appdata_dir() / 'logs'}",
                "Fatal Error", 0x10,
            )
        raise
```

- [ ] **Step 2: Manual smoke test**

```powershell
python run_tray.py
```
Expected: log file at `%APPDATA%\Andent Web\logs\andent_web.log`, tray icon, browser opens to /setup. Run it again immediately — second instance should show "already running" dialog and exit.

- [ ] **Step 3: Commit**

```powershell
git add run_tray.py
git commit -m "feat: add bulletproof tray launcher with mutex, logging, LAN detection"
```

---

## Task 7: Updater (with retry + safe location)

**Files:** `scripts/updater.py`

- [ ] **Step 1: Create `scripts/updater.py`**

```python
"""Andent Web self-updater. Runs out-of-process so the main EXE can be replaced."""
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--src", required=True)
    parser.add_argument("--dst", required=True)
    args = parser.parse_args()

    log_path = Path(args.dst).parent / "andent_updater.log"
    logging.basicConfig(filename=str(log_path), level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    import psutil
    deadline = time.time() + 30
    while time.time() < deadline:
        if not psutil.pid_exists(args.pid):
            break
        time.sleep(0.3)
    logging.info("Main process %s exited (or timeout)", args.pid)

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            shutil.copy2(args.src, args.dst)
            logging.info("Copy succeeded on attempt %d", attempt + 1)
            break
        except Exception as exc:
            last_err = exc
            logging.warning("Copy attempt %d failed: %s", attempt + 1, exc)
            time.sleep(1)
    else:
        logging.error("All copy attempts failed: %s", last_err)
        sys.exit(1)

    DETACHED = 0x00000008
    NO_WINDOW = 0x08000000
    subprocess.Popen([args.dst], creationflags=DETACHED | NO_WINDOW)
    logging.info("Relaunched %s", args.dst)
    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Sanity check**

```powershell
python scripts/updater.py --pid 99999 --src nonexistent.exe --dst y.exe
# Expected: exit code 1, log entries written
```

- [ ] **Step 3: Commit**

```powershell
git add scripts/updater.py
git commit -m "feat: add updater with 3x retry and safe relaunch"
```

---

## Task 8: PyInstaller Specs (with splash, .omx, multipart)

**Files:** `andent_web.spec`, `andent_updater.spec`

Critical fixes vs original:
- `('.omx', '.omx')` in datas (needed for material label catalog)
- `Splash(...)` block + `splash_binaries` (PyInstaller 6.x splash API)
- Hidden imports for `multipart`, `pydantic_core._pydantic_core`, `app.services.*`
- Updater spec uses `console=True` so AV diagnostic output is visible if it fails

- [ ] **Step 1: `andent_updater.spec`**

```python
from PyInstaller.building.build_main import Analysis, PYZ, EXE

a = Analysis(
    ['scripts/updater.py'], pathex=['.'],
    binaries=[], datas=[],
    hiddenimports=['psutil'],
    excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='Andent_Updater',
    debug=False, strip=False, upx=False,
    console=True,
    disable_windowed_traceback=False,
)
```

- [ ] **Step 2: `andent_web.spec`** (with splash)

```python
import re
from pathlib import Path
from PyInstaller.building.build_main import Analysis, PYZ, EXE, Splash

version = re.search(
    r'__version__\s*=\s*["\']([^"\']+)["\']',
    Path('app/version.py').read_text(),
).group(1)

a = Analysis(
    ['run_tray.py'], pathex=['.'],
    binaries=[('Andent_Updater.exe', '.')],
    datas=[
        ('app/static', 'app/static'),
        ('.omx', '.omx'),
    ],
    hiddenimports=[
        'uvicorn.lifespan.on', 'uvicorn.loops.auto', 'uvicorn.loops.asyncio',
        'uvicorn.protocols.websockets.auto', 'uvicorn.protocols.http.auto',
        'anyio._backends._asyncio',
        'pystray._win32', 'PIL._imagingtk',
        'multipart', 'multipart.multipart',
        'pydantic_core._pydantic_core',
        'app.routers.setup', 'app.routers.uploads', 'app.routers.metrics',
        'app.routers.preform_setup', 'app.routers.print_queue',
        'app.services.preform_setup_service', 'app.services.preform_client',
        'app.services.preset_catalog', 'app.services.print_queue_service',
        'app.services.build_planning', 'app.services.classification',
        'app.services.volume_enrichment',
        'app.logging_config', 'app.state', 'app.version',
    ],
    excludes=['tkinter', 'matplotlib', 'scipy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'],
    noarchive=False,
)
pyz = PYZ(a.pure)

splash = Splash(
    'app/static/splash.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(120, 290),
    text_size=12,
    text_color='black',
    text_default='Starting Andent Web…',
    minify_script=True,
)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    splash, splash.binaries,
    [],
    name=f'Andent_Web_v{version}',
    debug=False, strip=False, upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    version='version_info.txt',
    icon=None,
)
```

- [ ] **Step 3: Commit**

```powershell
git add andent_web.spec andent_updater.spec
git commit -m "feat: PyInstaller specs with splash, .omx data, complete hidden imports"
```

---

## Task 9: Build Script + .gitignore

**Files:** `scripts/builders/__init__.py`, `scripts/builders/build_deployment.py`, `.gitignore`

- [ ] **Step 1: `.gitignore` additions**

Append to `.gitignore`:
```
# PyInstaller build artifacts
/version_info.txt
/Andent_Updater.exe
/build/
/dist/
*.spec.bak
```

- [ ] **Step 2: `scripts/builders/__init__.py`** — empty

- [ ] **Step 3: `scripts/builders/build_deployment.py`**

```python
"""Build Andent Web Windows EXE."""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERSION_FILE = REPO_ROOT / "app" / "version.py"
VERSION_INFO_FILE = REPO_ROOT / "version_info.txt"

VERSION_INFO_TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({tuple_str}),
    prodvers=({tuple_str}),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(u'040904B0', [
        StringStruct(u'CompanyName', u'Harwav'),
        StringStruct(u'FileDescription', u'Andent Web Server'),
        StringStruct(u'FileVersion', u'{dot_str}'),
        StringStruct(u'InternalName', u'andent_web'),
        StringStruct(u'LegalCopyright', u'Harwav'),
        StringStruct(u'OriginalFilename', u'Andent_Web_v{version}.exe'),
        StringStruct(u'ProductName', u'Andent Web'),
        StringStruct(u'ProductVersion', u'{dot_str}'),
      ])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""


def read_version() -> str:
    text = VERSION_FILE.read_text()
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    if not m:
        raise ValueError("__version__ not found")
    return m.group(1)


def write_version(version: str) -> None:
    VERSION_FILE.write_text(f'__version__ = "{version}"\n')


def write_version_info(version: str) -> None:
    parts = (version.split(".") + ["0", "0", "0", "0"])[:4]
    tuple_str = ", ".join(parts)
    dot_str = ".".join(parts)
    VERSION_INFO_FILE.write_text(VERSION_INFO_TEMPLATE.format(
        tuple_str=tuple_str, dot_str=dot_str, version=version,
    ))


def run(cmd: list[str]) -> None:
    print(f"[build] {' '.join(cmd)}")
    if subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode != 0:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=None)
    args = parser.parse_args()

    version = args.version or read_version()
    print(f"[build] Building Andent Web v{version}")

    write_version(version)
    write_version_info(version)

    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "andent_updater.spec"])
    updater_src = REPO_ROOT / "dist" / "Andent_Updater.exe"
    updater_dst = REPO_ROOT / "Andent_Updater.exe"
    if updater_src.exists():
        shutil.copy2(str(updater_src), str(updater_dst))

    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "andent_web.spec"])

    exe_path = REPO_ROOT / "dist" / f"Andent_Web_v{version}.exe"
    if not exe_path.exists():
        print(f"[build] ERROR: {exe_path} not found", file=sys.stderr)
        sys.exit(1)

    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"[build] Built: {exe_path} ({size_mb:.1f} MB)")
    if size_mb < 40:
        print(f"[build] WARNING: EXE suspiciously small ({size_mb:.1f} MB)")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Local build smoke test**

```powershell
python scripts/builders/build_deployment.py --version 1.0.0
# Expected: dist/Andent_Web_v1.0.0.exe ~80-120 MB, completes in 1-3 min
```

- [ ] **Step 5: Commit**

```powershell
git add .gitignore scripts/builders/__init__.py scripts/builders/build_deployment.py
git commit -m "feat: add build script with templated version info and .gitignore"
```

---

## Task 10: GitHub Actions

**Files:** `.github/workflows/build-windows.yml`

- [ ] **Step 1: `.github/workflows/build-windows.yml`**

```yaml
name: Build Windows EXE

on:
  push:
    tags: ['v*']
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
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Verify imports load (catch hidden import errors before PyInstaller)
        run: python -c "import app.main, app.routers.setup, app.services.preform_setup_service, multipart; print('imports ok')"

      - name: Build EXE
        run: python scripts/builders/build_deployment.py

      - name: Extract version
        id: version
        shell: pwsh
        run: |
          $v = python -c "from app.version import __version__; print(__version__)"
          echo "version=$v" >> $env:GITHUB_OUTPUT

      - name: Verify EXE size
        shell: pwsh
        run: |
          $exe = "dist/Andent_Web_v${{ steps.version.outputs.version }}.exe"
          if (-not (Test-Path $exe)) { Write-Error "EXE not found: $exe"; exit 1 }
          $sizeMB = (Get-Item $exe).Length / 1MB
          Write-Host "EXE size: $sizeMB MB"
          if ($sizeMB -lt 40) { Write-Error "EXE too small ($sizeMB MB)"; exit 1 }

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: Andent_Web_v${{ steps.version.outputs.version }}
          path: dist/Andent_Web_v${{ steps.version.outputs.version }}.exe

      - name: Create GitHub Release
        if: startsWith(github.ref, 'refs/tags/v') || github.event.inputs.create_release == 'true'
        uses: softprops/action-gh-release@v2
        with:
          repository: Harwav/Andent_Releases
          tag_name: v${{ steps.version.outputs.version }}
          name: Andent Web v${{ steps.version.outputs.version }}
          files: dist/Andent_Web_v${{ steps.version.outputs.version }}.exe
          token: ${{ secrets.RELEASES_REPO_TOKEN }}
```

- [ ] **Step 2: Pre-flight checklist (BEFORE first tag push)**
  - Verify `Harwav/Andent_Releases` repo exists
  - Verify `RELEASES_REPO_TOKEN` is set in repo secrets with `contents: write` on the releases repo

- [ ] **Step 3: Commit**

```powershell
git add .github/workflows/build-windows.yml
git commit -m "feat: add Windows EXE CI build and release workflow"
```

---

## Task 11: End-to-End Verification

- [ ] **Step 1: Full test suite**
```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"; python -m pytest tests/ -q
```

- [ ] **Step 2: Dev smoke test**
```powershell
python run_tray.py
```
Verify: log file appears, tray icon shows, browser opens to /setup, drop a real PreFormServer ZIP → installs → step 3 (LAN consent) appears → click "Allow LAN Access" → step 4 shows correct LAN URL → "Open Andent Web" opens main app → tray "View Logs" opens log folder → "Quit" exits cleanly. Then run again — confirm "already running" dialog.

- [ ] **Step 3: PyInstaller build**
```powershell
python scripts/builders/build_deployment.py --version 1.0.0
```
Then double-click `dist\Andent_Web_v1.0.0.exe`:
  - Splash appears within 200ms
  - Tray icon appears within 10s
  - Wizard works end-to-end
  - Verify `%APPDATA%\Andent Web\logs\andent_web.log` exists with startup info

- [ ] **Step 4: LAN access from second machine**
```powershell
# On second machine on same network
curl http://<server-LAN-IP>:8090/health/live
# Expected: {"alive": true}
```

- [ ] **Step 5: Update flow**
Set `__version__ = "0.0.1"` temporarily, rebuild, run. Should see update notification within 5s. Restore `1.0.0` after.

- [ ] **Step 6: Single-instance lock**
With Andent running, double-click the EXE again. Expected: dialog box, no second tray icon.

- [ ] **Step 7: Final commit**
```powershell
git add -A
git commit -m "feat: complete bulletproof Windows EXE deployment"
```

---

## Risk Register (residual)

| Risk | Mitigation in plan | Residual |
|------|-------------------|----------|
| AV/SmartScreen quarantine | Wizard explainer + retry copy in updater | First ~50 installs see warning |
| Slow HDD cold start | Splash screen masks 5-10s extract | User can still close splash by accident |
| Multi-homed LAN IP wrong | RFC1918-prefer detection | Wizard step 3 still trusts the value |
| Patient data on hostile Wi-Fi | Loopback during setup; explicit consent step | Once allowed, no per-request auth |
| GitHub rate limit | 24h disk cache | Shared NAT lab still hits it on first day |
| Updater fails | Retry 3x + log file beside binary | `andent_updater.log` requires user to find it |
| Wizard JS bug | 4-step flow, fewer race surfaces than 3-step | Manual test only, no Playwright |

---

## What's still NOT in scope (be explicit)

- **Auth / login** — accepted "trust the LAN" per user decision
- **Code signing** — accepted "ship unsigned for v1"
- **Crash telemetry** — local logs only, no Sentry
- **NSIS installer** — single-file EXE only
- **Auto-restart on crash** — if uvicorn dies the tray stays but app is dead
- **macOS / Linux builds** — Windows only

These are listed so a future planner doesn't accidentally claim they're done.
