# Windows EXE Deployment Design
**Date:** 2026-04-29  
**Status:** Approved  

---

## Context

FormFlow is a FastAPI + SQLite local server that runs on a dental lab workstation and is accessed by other lab computers over LAN. Currently it requires Python, manual dependency installation, and running uvicorn from a terminal — a non-starter for non-technical dental lab technicians.

The goal is to ship a single-file Windows EXE that a technician can download from a GitHub Releases page, double-click, and be up and running within minutes. The reference model is YF_ERP (at `c:/Users/Marcus/Documents/YF_ERP`), which uses the same pattern: PyInstaller + pystray tray icon + auto-browser-launch + GitHub Releases distribution.

---

## Chosen Approach: Browser-Based Setup Wizard

Rather than Tkinter dialogs for first-run setup (as YF_ERP uses), FormFlow serves its setup wizard through the FastAPI app itself at a `/setup` route. This keeps the wizard visually consistent with the main app (same `styles.css`) and avoids a Tkinter dependency.

---

## Architecture

### New Components

| Component | File | Purpose |
|-----------|------|---------|
| EXE entry point | `run_tray.py` | Starts uvicorn in background thread, creates pystray tray, opens browser |
| Setup wizard route | `app/routers/setup.py` | Serves `/setup` HTML; 302-redirects to `/` when already ready |
| Setup wizard page | `app/static/setup.html` | Browser-based 3-step setup UI |
| Version file | `app/version.py` | Single source of truth: `__version__ = "1.0.0"` |
| PyInstaller spec | `formflow.spec` | Bundles everything into single EXE |
| Build script | `scripts/builders/build_deployment.py` | Updates version in spec + version_info.txt, runs PyInstaller |
| Windows version info | `version_info.txt` | Windows EXE metadata (antivirus friendliness) |
| Update helper | `scripts/updater.py` + `formflow_updater.spec` | Compiled as a second small EXE (`FormFlow_Updater.exe`), bundled inside main EXE via PyInstaller `datas`; waits for current process exit, replaces EXE, relaunches |
| GitHub Actions workflow | `.github/workflows/build-windows.yml` | tag push → PyInstaller → GitHub Release |

### Runtime Directory (EXE mode)

```
%APPDATA%\FormFlow\
  ├─ PreFormServer\           ← managed PreFormServer install (already wired in config)
  │  ├─ PreFormServer.exe
  │  ├─ version.txt
  │  └─ hoops\
  ├─ data\
  │  ├─ formflow.db         ← SQLite DB (moved from ./data/ in EXE mode)
  │  ├─ uploads\
  │  └─ screenshots\
  └─ logs\
     └─ formflow.log
```

In EXE mode, `FORMFLOW_WEB_DATA_DIR` is set to `%APPDATA%\FormFlow\data` so data survives EXE replacement during updates. In dev mode, the existing `./data/` default remains unchanged.

### Double-Click Launch Sequence

```
EXE launches
  → run_tray.py
  → configure env vars for EXE mode (DATA_DIR → AppData, HOST → 0.0.0.0)
  → start uvicorn on 0.0.0.0:8090 in background thread
  → create pystray tray icon (green circle)
  → GET /api/preform-setup/status
      → readiness == "not_installed"  → webbrowser.open("http://localhost:8090/setup")
      → readiness == "ready"          → webbrowser.open("http://localhost:8090/")
  → schedule background update check (startup + every 24h)
```

---

## Setup Wizard (`/setup`)

### Guard

`GET /setup` checks `preform_setup_state.readiness`. If `"ready"`, immediately 302-redirects to `/`. This prevents re-entering the wizard after setup is complete.

### Three Steps

**Step 1 — Welcome**
- FormFlow logo, one-sentence description
- Explains that the PreFormServer ZIP (from Formlabs) is required
- Single "Get Started →" button

**Step 2 — Install PreFormServer**
- Drag-and-drop / browse file picker for the PreFormServer `.zip`
- On submit: calls existing `POST /api/preform-setup/install-from-zip` (no new backend endpoint)
- Progress spinner + status text while polling `GET /api/preform-setup/status`
- Human-readable error messages for known failure codes:
  - `bad_zip` → "That file doesn't look like a valid PreFormServer ZIP. Please download it from Formlabs."
  - `incompatible_version` → "PreFormServer v{version} is not supported. Minimum required: v{min}."
  - `missing_install` → "Installation failed. Please try again or contact support."
- On success: green checkmark, "PreFormServer v{version} installed"

**Step 3 — Done**
- "Setup complete. FormFlow is running."
- Displays LAN address (`http://{local_ip}:8090`) for sharing with other workstations
- "Open FormFlow →" button → navigates to `/`

### LAN IP Detection

`run_tray.py` detects the machine's LAN IP at startup via `socket.getsockopt` / connecting to `8.8.8.8:80` (no traffic sent) and stores it on `app.state.lan_ip`. The setup done page and tray menu both read this value.

---

## Tray Icon

**Library:** `pystray`  
**Icon:** Green circle (PNG, 64×64, bundled in EXE via PyInstaller `datas`)

**Menu:**

```
Open FormFlow
─────────────────────────────
LAN: http://192.168.x.x:8090   [disabled label]
─────────────────────────────
Check for Updates
Version: v1.0.0                [disabled label]
─────────────────────────────
Quit
```

- Left-click on tray icon → Open FormFlow
- Quit → graceful uvicorn shutdown then `sys.exit(0)`

---

## Auto-Updater

### Check

On startup and every 24 hours, a background thread calls:
```
GET https://api.github.com/repos/Harwav/FormFlow_Releases/releases/latest
```
Compares `tag_name` (e.g., `v1.2.0`) against current `__version__`. If newer, stores the download URL.

### Notify

Windows balloon notification via `pystray` notification or `ctypes` MessageBox:  
> "FormFlow v1.2.0 is available. Click 'Check for Updates' in the tray to install."

### Download & Replace

1. User clicks "Check for Updates" in tray menu
2. Confirmation dialog: "Update to v1.2.0 and restart FormFlow?"
3. Downloads new EXE to `%TEMP%\formflow_update.exe`
4. Extracts `FormFlow_Updater.exe` from PyInstaller bundle to `%TEMP%\` and launches it as a detached process with args: `--pid {current_pid} --src %TEMP%\formflow_update.exe --dst {current_exe_path}`:
   - Waits for current PID to exit (polls with `psutil.pid_exists`)
   - Copies `formflow_update.exe` over the current EXE path
   - Relaunches the EXE
5. Current process calls `tray.stop()` then exits

### Releases Repo

Public repo: `Harwav/FormFlow_Releases` (mirrors YF_ERP pattern with `Harwav/YF_ERP_Releases`).
EXE asset name: `FormFlow_v{version}.exe`

---

## Build Pipeline

### Version Management

- Single source: `app/version.py` — `__version__ = "1.0.0"` (semver, no build suffix)
- `scripts/builders/build_deployment.py` updates `formflow.spec` and `version_info.txt` before PyInstaller runs

### PyInstaller Spec (`formflow.spec`)

Key settings mirroring YF_ERP's proven `.spec`:
```python
name='FormFlow_v{version}'
console=False          # no terminal window
runtime_tmpdir=None    # use %TEMP% (always writable)
strip=False            # Windows DLL compat
upx=False              # Windows DLL compat
datas=[
    ('app/static', 'app/static'),   # HTML/JS/CSS
    ('app/static/tray_icon.png', 'app/static'),
]
hiddenimports=[
    'uvicorn.lifespan.on',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.protocols.http.auto',
    'anyio._backends._asyncio',
    'pystray._win32',
    'PIL._imagingtk',
]
```

Bundles `vcruntime140.dll` and `vcruntime140_1.dll` explicitly (CI build compatibility, same as YF_ERP).

### GitHub Actions (`.github/workflows/build-windows.yml`)

Trigger: push `v*` tag or manual `workflow_dispatch`.

Steps:
1. Checkout code
2. Setup Python 3.13 (pinned)
3. `pip install -r requirements.txt`
4. `python scripts/builders/build_deployment.py` (runs PyInstaller)
5. Verify EXE exists and size > 40 MB
6. Extract version from `app/version.py`
7. Create GitHub Release on `Harwav/FormFlow_Releases` with EXE as asset

---

## Configuration in EXE Mode

`run_tray.py` sets these environment variables before importing the app, so no `config.env` file is needed for basic operation:

```python
os.environ.setdefault("FORMFLOW_WEB_HOST", "0.0.0.0")          # LAN-accessible
os.environ.setdefault("FORMFLOW_WEB_PORT", "8090")
os.environ.setdefault("FORMFLOW_WEB_DATA_DIR", str(appdata_dir / "data"))
os.environ.setdefault("FORMFLOW_WEB_DATABASE_PATH", str(appdata_dir / "data" / "formflow.db"))
os.environ.setdefault("FORMFLOW_WEB_PRINT_DISPATCH_MODE", "real")
```

Advanced users can place a `config.env` file next to the EXE to override any setting (same pattern as YF_ERP).

---

## Files Modified / Created

### New files
- `run_tray.py`
- `app/version.py`
- `app/routers/setup.py` — includes `GET /setup` (wizard HTML, redirects to `/` if ready) and `GET /api/setup/lan-ip` (returns `{"lan_ip": "192.168.x.x", "port": 8090}`)
- `app/static/setup.html`
- `app/static/tray_icon.png`
- `formflow.spec`
- `formflow_updater.spec`
- `version_info.txt`
- `scripts/builders/build_deployment.py`
- `scripts/updater.py` (compiled to `FormFlow_Updater.exe` via `formflow_updater.spec`, bundled inside main EXE)
- `.github/workflows/build-windows.yml`

### Modified files
- `app/main.py` — register setup router; set `app.state.lan_ip`
- `app/config.py` — no changes needed (AppData paths already wired)
- `requirements.txt` — add `pystray`, `pillow` (for tray icon rendering)

### Unchanged
- All existing routers, services, database, core logic — zero changes required
- `app/static/index.html`, `app.js`, `styles.css` — wizard uses same CSS but separate HTML file

---

## Verification

1. **Dev smoke test:** `python run_tray.py` — tray icon appears, browser opens to `/setup`, wizard completes, redirects to `/`
2. **LAN test:** from a second machine, browse to `http://{server-LAN-IP}:8090` — app loads
3. **Update test:** set version in `app/version.py` to `0.0.1`, confirm update notification appears; confirm EXE replacement works
4. **PyInstaller smoke test:** `pyinstaller formflow.spec` — EXE launches, tray appears, app functions
5. **Existing tests:** `pytest tests/ -q` — all pass (no existing tests affected)
6. **E2E:** `npm run test:release-gate` — passes against EXE-launched server
