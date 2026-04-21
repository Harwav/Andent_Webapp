# PreFormServer Setup Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a managed Windows PreFormServer setup flow with ZIP install/replacement, readiness persistence, version gating, service control, and a queue UI that blocks print actions until the managed dependency is ready.

**Architecture:** Add one backend manager service that owns the canonical managed install path, ZIP validation, staged extraction, process lifecycle, health/version checks, and readiness persistence. Expose that manager through dedicated API routes, then update the existing queue page to show setup state, render a first-run wizard plus maintenance panel, and intercept `Send to Print` whenever readiness is not `ready`.

**Tech Stack:** FastAPI, SQLite, Pydantic, pytest, vanilla JS, Windows-managed filesystem/process flow, existing PreFormServer HTTP client

---

## File Structure

### New Files

- `app/services/preform_setup_service.py`
  Owns managed install resolution, ZIP validation, staged extraction, replace flow, process control, health checks, version parsing, compatibility checks, and readiness persistence helpers.
- `app/routers/preform_setup.py`
  Owns the setup-center API surface for status, install, replace, start, stop, restart, and recheck.
- `tests/test_preform_setup.py`
  Owns TDD coverage for setup status, ZIP validation/install, version gating, and print blocking before readiness.

### Existing Files To Modify

- `app/config.py`
  Add managed install, port, timeout, and compatibility settings.
- `app/database.py`
  Persist PreFormServer readiness state and last known error details.
- `app/schemas.py`
  Add setup-status and setup-action response models.
- `app/main.py`
  Register the new setup router.
- `app/services/print_queue_service.py`
  Enforce a hard readiness gate before live PreForm handoff.
- `app/routers/uploads.py`
  Return a setup-related HTTP conflict instead of raw handoff failure when readiness is blocked.
- `app/static/index.html`
  Add the setup banner, setup center, and first-run wizard shell.
- `app/static/app.js`
  Load setup status, drive ZIP upload/actions, disable or intercept print actions, and render degraded-state UI.
- `app/static/styles.css`
  Style the setup center, banner, wizard overlay, and readiness status surfaces.

## Task 1: Add Readiness Persistence And Status Models

**Files:**
- Modify: `app/config.py`
- Modify: `app/database.py`
- Modify: `app/schemas.py`
- Test: `tests/test_preform_setup.py`

- [ ] **Step 1: Write the failing readiness-status test**

```python
def test_setup_status_defaults_to_not_installed(tmp_path):
    settings = _build_settings(tmp_path)
    init_db(settings)

    status = get_preform_setup_status(settings)

    assert status.readiness == "not_installed"
    assert status.install_path == str(settings.preform_managed_dir)
    assert status.managed_executable_path == str(settings.preform_managed_executable)
    assert status.detected_version is None
    assert status.last_error_code is None
```

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_preform_setup.py::test_setup_status_defaults_to_not_installed -q`
Expected: FAIL because the setup status model and persistence surface do not exist yet.

- [ ] **Step 2: Add config fields for the managed install contract**

```python
appdata_root = Path(os.getenv("ANDENT_WEB_APPDATA_DIR", os.getenv("APPDATA", resolved_data_dir / "appdata")))
managed_root = appdata_root / "Andent Web"
managed_dir = managed_root / "PreFormServer"

return Settings(
    ...,
    appdata_dir=managed_root,
    preform_server_port=int(os.getenv("ANDENT_WEB_PREFORM_PORT", "44388")),
    preform_managed_dir=managed_dir,
    preform_managed_executable=managed_dir / "PreFormServer.exe",
    preform_server_startup_timeout_s=int(os.getenv("ANDENT_WEB_PREFORM_STARTUP_TIMEOUT_S", "30")),
    preform_server_shutdown_timeout_s=int(os.getenv("ANDENT_WEB_PREFORM_SHUTDOWN_TIMEOUT_S", "10")),
    preform_min_zip_size_bytes=int(os.getenv("ANDENT_WEB_PREFORM_MIN_ZIP_SIZE_BYTES", str(10 * 1024 * 1024))),
    preform_min_supported_version=os.getenv("ANDENT_WEB_PREFORM_MIN_VERSION", "3.55.0"),
    preform_max_supported_version=os.getenv("ANDENT_WEB_PREFORM_MAX_VERSION") or None,
)
```

- [ ] **Step 3: Add one persisted setup-state table plus row mapping**

```python
CREATE TABLE IF NOT EXISTS preform_setup_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    readiness TEXT NOT NULL,
    install_path TEXT NOT NULL,
    managed_executable_path TEXT NOT NULL,
    detected_version TEXT,
    last_health_check_at TEXT,
    last_error_code TEXT,
    last_error_message TEXT,
    active_configured_source INTEGER NOT NULL DEFAULT 1,
    process_id INTEGER,
    updated_at TEXT NOT NULL
)
```

```python
def save_preform_setup_state(settings: Settings, **changes: object) -> None:
    now = _now_iso()
    current = get_preform_setup_state(settings)
    payload = {
        "readiness": changes.get("readiness", current["readiness"]),
        "install_path": changes.get("install_path", current["install_path"]),
        "managed_executable_path": changes.get("managed_executable_path", current["managed_executable_path"]),
        "detected_version": changes.get("detected_version", current["detected_version"]),
        "last_health_check_at": changes.get("last_health_check_at", current["last_health_check_at"]),
        "last_error_code": changes.get("last_error_code", current["last_error_code"]),
        "last_error_message": changes.get("last_error_message", current["last_error_message"]),
        "active_configured_source": 1 if changes.get("active_configured_source", current["active_configured_source"]) else 0,
        "process_id": changes.get("process_id", current["process_id"]),
        "updated_at": now,
    }
```

- [ ] **Step 4: Add the setup schemas**

```python
PreFormReadiness = Literal["not_installed", "installed_not_running", "incompatible_version", "ready", "failed"]


class PreFormSetupStatus(BaseModel):
    readiness: PreFormReadiness
    install_path: str
    managed_executable_path: str
    detected_version: str | None = None
    expected_version_min: str
    expected_version_max: str | None = None
    active_configured_source: bool = True
    is_running: bool = False
    last_health_check_at: str | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None


class PreFormSetupActionResponse(BaseModel):
    status: PreFormSetupStatus
    message: str
```

- [ ] **Step 5: Run the readiness-status test**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_preform_setup.py::test_setup_status_defaults_to_not_installed -q`
Expected: PASS.

## Task 2: Add The Managed Install And Readiness Service

**Files:**
- Create: `app/services/preform_setup_service.py`
- Test: `tests/test_preform_setup.py`

- [ ] **Step 1: Write the failing ZIP-install and compatibility tests**

```python
def test_install_from_zip_extracts_managed_copy_and_marks_ready(tmp_path):
    settings = _build_settings(tmp_path)
    init_db(settings)
    archive_path = _build_preform_zip(tmp_path, version_text="3.57.2.624")

    manager = PreFormSetupService(settings)
    manager._launch_process = lambda executable: 4242
    manager._probe_server = lambda: {"healthy": True, "version": "3.57.2.624"}

    status = manager.install_from_zip(archive_path)

    assert status.readiness == "ready"
    assert settings.preform_managed_executable.exists()
    assert status.detected_version == "3.57.2.624"


def test_install_from_zip_rejects_archive_without_preformserver_exe(tmp_path):
    settings = _build_settings(tmp_path)
    init_db(settings)
    archive_path = _build_invalid_zip(tmp_path)

    manager = PreFormSetupService(settings)

    with pytest.raises(PreFormSetupError) as exc_info:
        manager.install_from_zip(archive_path)

    assert exc_info.value.code == "bad_zip"
```

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_preform_setup.py -q`
Expected: FAIL because the service does not exist yet.

- [ ] **Step 2: Implement ZIP validation, staging, replace, and version checks**

```python
class PreFormSetupError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class PreFormSetupService:
    def install_from_zip(self, archive_path: Path) -> PreFormSetupStatus:
        self._validate_zip(archive_path)
        staged_dir = self._extract_to_staging(archive_path)
        payload_dir = self._resolve_payload_root(staged_dir)
        self.stop(ignore_missing=True)
        self._replace_managed_install(payload_dir)
        self.start()
        return self.recheck()
```

```python
def _validate_zip(self, archive_path: Path) -> None:
    if not archive_path.exists():
        raise PreFormSetupError("bad_zip", "Selected ZIP file does not exist.")
    if archive_path.suffix.lower() != ".zip":
        raise PreFormSetupError("bad_zip", "Select a .zip package for PreFormServer.")
    if archive_path.stat().st_size < self.settings.preform_min_zip_size_bytes:
        raise PreFormSetupError("bad_zip", "Selected ZIP is smaller than the minimum supported package size.")
    with zipfile.ZipFile(archive_path) as archive:
        members = [Path(name) for name in archive.namelist() if not name.endswith("/")]
    if "PreFormServer.exe" not in {member.name for member in members}:
        raise PreFormSetupError("bad_zip", "ZIP does not contain a supported PreFormServer.exe layout.")
```

- [ ] **Step 3: Implement start, stop, restart, recheck, and readiness derivation**

```python
def recheck(self) -> PreFormSetupStatus:
    if not self.settings.preform_managed_executable.exists():
        return self._persist_status(readiness="not_installed", error_code=None, error_message=None, detected_version=None, is_running=False)

    probe = self._probe_server()
    if not probe["healthy"]:
        return self._persist_status(readiness="installed_not_running", error_code=probe["code"], error_message=probe["message"], detected_version=None, is_running=False)

    version = probe["version"]
    if not self._version_is_supported(version):
        return self._persist_status(readiness="incompatible_version", error_code="incompatible_version", error_message=f"Detected PreFormServer {version} is outside the supported range.", detected_version=version, is_running=True)

    return self._persist_status(readiness="ready", error_code=None, error_message=None, detected_version=version, is_running=True)
```

- [ ] **Step 4: Run the setup-service tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_preform_setup.py -q`
Expected: PASS.

## Task 3: Expose Setup Routes And Block Print Until Ready

**Files:**
- Create: `app/routers/preform_setup.py`
- Modify: `app/main.py`
- Modify: `app/services/print_queue_service.py`
- Modify: `app/routers/uploads.py`
- Test: `tests/test_preform_setup.py`

- [ ] **Step 1: Write the failing API tests for status, install, and blocked print**

```python
def test_status_route_returns_not_installed_for_fresh_app(tmp_path):
    client, settings = _build_client(tmp_path)

    response = client.get("/api/preform-setup/status")

    assert response.status_code == 200
    assert response.json()["readiness"] == "not_installed"


def test_send_to_print_returns_409_when_preform_not_ready(tmp_path):
    client, settings = _build_client_with_ready_row(tmp_path)

    response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": [1]})

    assert response.status_code == 409
    assert "PreFormServer setup is required" in response.json()["detail"]
```

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_preform_setup.py::test_status_route_returns_not_installed_for_fresh_app tests/test_preform_setup.py::test_send_to_print_returns_409_when_preform_not_ready -q`
Expected: FAIL because the route surface and readiness gate do not exist yet.

- [ ] **Step 2: Add the setup router**

```python
router = APIRouter(prefix="/api/preform-setup", tags=["preform-setup"])


@router.get("/status", response_model=PreFormSetupStatus)
async def get_status(request: Request) -> PreFormSetupStatus:
    return PreFormSetupService(request.app.state.settings).recheck()


@router.post("/install-from-zip", response_model=PreFormSetupActionResponse)
async def install_from_zip(request: Request, package: UploadFile = File(...)) -> PreFormSetupActionResponse:
    status = await _save_upload_then_call(request.app.state.settings, package, "install")
    return PreFormSetupActionResponse(status=status, message="PreFormServer installed and verified.")
```

- [ ] **Step 3: Enforce the hard gate before handoff**

```python
def assert_preform_ready(settings: "Settings") -> None:
    status = PreFormSetupService(settings).recheck()
    if status.readiness != "ready":
        raise ValueError(f"PreFormServer setup is required before printing ({status.readiness}).")


def send_ready_rows_to_print(settings: "Settings", row_ids: list[int]) -> list["ClassificationRow"]:
    assert_preform_ready(settings)
    ...
```

- [ ] **Step 4: Run the route and gate tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_preform_setup.py -q`
Expected: PASS.

## Task 4: Add The Setup Center, First-Run Wizard, And UI Gating

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`

- [ ] **Step 1: Add the setup-center HTML shell**

```html
<section id="preform-banner" class="setup-banner hidden"></section>

<section id="preform-setup-panel" class="panel setup-panel">
  <div class="setup-panel-header">
    <div>
      <p class="eyebrow">PreFormServer</p>
      <h2>Setup Center</h2>
    </div>
    <span id="preform-readiness-pill" class="status-pill">Checking</span>
  </div>
  <p id="preform-summary" class="setup-summary"></p>
  <div class="setup-meta-grid">
    <div><span>Install Path</span><strong id="preform-install-path"></strong></div>
    <div><span>Detected Version</span><strong id="preform-version"></strong></div>
  </div>
  <div class="setup-actions">
    <input id="preform-zip-input" type="file" accept=".zip" hidden>
    <button id="preform-install-button" class="primary-button" type="button">Install or Replace ZIP</button>
    <button id="preform-start-button" class="secondary-button" type="button">Start</button>
    <button id="preform-restart-button" class="secondary-button" type="button">Restart</button>
    <button id="preform-recheck-button" class="ghost-button" type="button">Re-check</button>
  </div>
</section>

<div id="preform-wizard" class="wizard-shell hidden" aria-hidden="true"></div>
```

- [ ] **Step 2: Load and render setup status in the frontend**

```javascript
state.preformSetup = { status: null, loading: false };

async function fetchPreformSetupStatus() {
    const response = await fetch("/api/preform-setup/status");
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.detail || "Could not load PreFormServer status.");
    }
    state.preformSetup.status = payload;
}

function canPrint() {
    return state.preformSetup.status?.readiness === "ready";
}
```

- [ ] **Step 3: Disable or intercept `Send to Print` when readiness is not ready**

```javascript
if (readyRows.length > 0) {
    const submitButton = document.createElement("button");
    submitButton.type = "button";
    submitButton.className = "primary-button";
    submitButton.textContent = canPrint()
        ? `Send to Print (${readyRows.length})`
        : `Setup Required (${readyRows.length})`;
    submitButton.disabled = !canPrint();
    submitButton.addEventListener("click", async () => {
        if (!canPrint()) {
            openPreformWizard();
            return;
        }
        ...
    });
}
```

- [ ] **Step 4: Add the wizard/degraded-state styling**

```css
.setup-banner { border: 1px solid var(--warn); background: var(--warn-soft); }
.setup-panel { display: grid; gap: 16px; }
.wizard-shell {
    position: fixed;
    inset: 0;
    z-index: 30;
    display: grid;
    place-items: center;
    background: rgba(17, 17, 16, 0.68);
}
.wizard-card {
    width: min(760px, calc(100vw - 32px));
    padding: 32px;
    border-radius: 18px;
    background: var(--surface);
    box-shadow: 0 24px 80px rgba(0, 0, 0, 0.24);
}
```

- [ ] **Step 5: Manual browser verification**

Run: `python -m uvicorn app.main:app --reload --port 8090`
Expected:
- Fresh app shows the setup center as `not_installed`.
- The wizard appears on first load until dismissed or setup completes.
- `Send to Print` is blocked until readiness becomes `ready`.

## Task 5: Verification Sweep

**Files:**
- Modify: none

- [ ] **Step 1: Run the focused setup tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_preform_setup.py tests/test_preform_handoff.py tests/test_print_queue.py -q`
Expected: PASS.

- [ ] **Step 2: Run the broader repository suite**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 3: Review the final diff**

Run: `git diff --stat`
Expected: diff includes setup service, setup router, config/schema/database changes, print gate changes, and queue UI updates.

## Self-Review

### Spec Coverage

This plan covers:

1. Canonical managed install path: Tasks 1 and 2
2. ZIP validation, staging, and replacement: Task 2
3. Version compatibility enforcement: Task 2
4. Persistent readiness state: Task 1
5. Dedicated setup API surface: Task 3
6. Hard print gate before handoff: Task 3
7. First-run wizard and persistent maintenance panel: Task 4
8. Degraded-state UI and queue messaging: Task 4
9. Focused and broader verification: Task 5

No design requirement is left without an implementation task.

### Placeholder Scan

Checked for `TBD`, `TODO`, unresolved “handle later” steps, and dangling type names. None remain.

### Type Consistency

The plan consistently uses:

1. `PreFormSetupService`
2. `PreFormSetupStatus`
3. `PreFormSetupActionResponse`
4. `assert_preform_ready()`
5. `preform_setup_state`

Those names stay aligned across config, persistence, API, service, and UI tasks.
