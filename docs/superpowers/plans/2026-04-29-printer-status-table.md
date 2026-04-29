# Printer Status Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the setup-center printer cards with a compact status table and display readable PreFormServer material names instead of raw material codes.

**Architecture:** Keep the existing `/api/preform-setup/printers` route as the single data source. Extend its normalized printer schema with explicit `material_name` and `material_code` fields while retaining `material` as a compatibility value. Update the vanilla JS renderer to use a semantic table and prefer readable material names.

**Tech Stack:** FastAPI, Pydantic, pytest, vanilla JavaScript, CSS.

---

## File Structure

- Modify `app/schemas.py`: add explicit material fields to `PreFormPrinterStatus`.
- Modify `app/routers/preform_setup.py`: normalize readable material names separately from raw material/tank codes.
- Modify `tests/test_preform_setup.py`: lock the API material-name preference and code fallback behavior.
- Modify `app/static/app.js`: replace card rendering with table rendering and status/material helper functions.
- Modify `app/static/styles.css`: replace printer-card styles with responsive table and status-pill styles.
- Modify `tests/test_frontend_static.py`: assert the frontend uses the table renderer and new CSS hooks.

No new files or dependencies are needed.

---

### Task 1: Normalize Printer Material Name And Code

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/routers/preform_setup.py`
- Test: `tests/test_preform_setup.py`

- [ ] **Step 1: Write failing API tests for material-name preference**

In `tests/test_preform_setup.py`, update `test_printers_route_returns_local_preform_devices` so the expected response includes the new fields:

```python
assert response.json() == {
    "printers": [
        {
            "device_id": "printer-01",
            "name": "Form 4B East",
            "model": "Form 4B",
            "status": "ready",
            "material": "Dental LT Clear",
            "material_name": "Dental LT Clear",
            "material_code": None,
            "metadata": {
                "device_id": "printer-01",
                "name": "Form 4B East",
                "status": "ready",
                "material": "Dental LT Clear",
                "model": "Form 4B",
            },
        }
    ],
    "available": True,
    "message": None,
}
```

In the `test_printers_route_unwraps_preform_devices_payload` mocked device, add a readable name beside the code:

```python
"tank_material_name": "High Temp Resin",
"tank_material_code": "FLTO1502",
```

Then replace the material assertion block with:

```python
assert payload["printers"][0]["material"] == "High Temp Resin"
assert payload["printers"][0]["material_name"] == "High Temp Resin"
assert payload["printers"][0]["material_code"] == "FLTO1502"
```

- [ ] **Step 2: Write failing API test for code-only fallback**

Add this test below `test_printers_route_unwraps_preform_devices_payload`:

```python
def test_printers_route_keeps_material_code_as_fallback(tmp_path, monkeypatch):
    from app.services.preform_client import PreFormClient
    from app.services.preform_setup_service import PreFormSetupService

    monkeypatch.setattr(
        PreFormSetupService,
        "_probe_server",
        lambda self: {
            "healthy": True,
            "version": "3.58.0.626",
            "code": None,
            "message": None,
        },
    )
    monkeypatch.setattr(
        PreFormClient,
        "list_devices",
        lambda self: {
            "count": 1,
            "devices": [
                {
                    "connection_type": "WIFI",
                    "id": "form-4b-ready",
                    "product_name": "Form 4B",
                    "status": "Ready",
                    "tank_material_code": "FLBMAM01",
                }
            ],
        },
    )

    client, _settings = _build_client(tmp_path)

    response = client.get("/api/preform-setup/printers")

    assert response.status_code == 200
    [printer] = response.json()["printers"]
    assert printer["material"] == "FLBMAM01"
    assert printer["material_name"] is None
    assert printer["material_code"] == "FLBMAM01"
```

- [ ] **Step 3: Run focused API tests and verify they fail**

Run:

```bash
pytest tests/test_preform_setup.py::test_printers_route_returns_local_preform_devices tests/test_preform_setup.py::test_printers_route_unwraps_preform_devices_payload tests/test_preform_setup.py::test_printers_route_keeps_material_code_as_fallback -v
```

Expected: failures showing missing `material_name` and `material_code` keys, plus the new fallback test failing before implementation.

- [ ] **Step 4: Extend the Pydantic schema**

In `app/schemas.py`, replace `PreFormPrinterStatus` with:

```python
class PreFormPrinterStatus(BaseModel):
    device_id: str | None = None
    name: str
    model: str | None = None
    status: str | None = None
    material: str | None = None
    material_name: str | None = None
    material_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 5: Add material normalization helpers**

In `app/routers/preform_setup.py`, add this import near the top:

```python
import re
```

Below `_first_text`, add:

```python
def _looks_like_material_code(value: str) -> bool:
    normalized = value.strip().upper()
    return bool(re.fullmatch(r"FL[A-Z0-9]{5,}", normalized))


def _first_readable_material_name(device: dict) -> str | None:
    for key in (
        "material_name",
        "tank_material_name",
        "resin_name",
        "display_material",
        "material_label",
        "material",
        "resin",
    ):
        value = _first_text(device, (key,))
        if value and not _looks_like_material_code(value):
            return value
    return None


def _first_material_code(device: dict) -> str | None:
    for key in (
        "material_code",
        "tank_material_code",
        "resin_code",
        "resin_material_code",
        "material",
        "resin",
    ):
        value = _first_text(device, (key,))
        if value and _looks_like_material_code(value):
            return value
    return None
```

- [ ] **Step 6: Use the new helpers in `_normalize_printer`**

In `app/routers/preform_setup.py`, replace the existing `material = _first_text(...)` block with:

```python
    material_name = _first_readable_material_name(device)
    material_code = _first_material_code(device)
    material = material_name or material_code
```

Then update the returned model:

```python
    return PreFormPrinterStatus(
        device_id=device_id,
        name=name or device_id or model or "Unnamed printer",
        model=model,
        status=status,
        material=material,
        material_name=material_name,
        material_code=material_code,
        metadata=device,
    )
```

- [ ] **Step 7: Run focused API tests and verify they pass**

Run:

```bash
pytest tests/test_preform_setup.py::test_printers_route_returns_local_preform_devices tests/test_preform_setup.py::test_printers_route_unwraps_preform_devices_payload tests/test_preform_setup.py::test_printers_route_keeps_material_code_as_fallback -v
```

Expected: all three tests pass.

- [ ] **Step 8: Commit API normalization**

Run:

```bash
git add app/schemas.py app/routers/preform_setup.py tests/test_preform_setup.py
git commit -m "Show readable printer materials from PreFormServer" -m "Printer status needs operator-readable material labels while preserving raw tank codes for fallback/debug use. The normalized setup-center printer payload now separates material_name from material_code and keeps the legacy material value populated from the best available display value.

Constraint: PreFormServer device payloads may expose either readable names, raw tank codes, or both.
Rejected: Hardcode a material-code lookup table | PreFormServer can provide readable names and hardcoding risks stale resin mappings.
Confidence: high
Scope-risk: narrow
Directive: Keep raw material codes out of the primary UI when material_name is present.
Tested: pytest tests/test_preform_setup.py::test_printers_route_returns_local_preform_devices tests/test_preform_setup.py::test_printers_route_unwraps_preform_devices_payload tests/test_preform_setup.py::test_printers_route_keeps_material_code_as_fallback -v"
```

---

### Task 2: Render Printers As A Compact Status Table

**Files:**
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_frontend_static.py`

- [ ] **Step 1: Write failing frontend static assertions**

In `tests/test_frontend_static.py`, update `test_setup_center_displays_local_printer_status` to:

```python
def test_setup_center_displays_local_printer_status():
    index_html = INDEX_HTML.read_text(encoding="utf-8")
    app_js = APP_JS.read_text(encoding="utf-8")
    styles_css = STYLES_CSS.read_text(encoding="utf-8")

    assert 'id="preform-printer-list"' in index_html
    assert 'id="preform-printer-refresh-button"' in index_html
    assert "fetchPreformPrinters" in app_js
    assert '"/api/preform-setup/printers"' in app_js
    assert "renderPreformPrinters" in app_js
    assert "formatPrinterMaterial" in app_js
    assert "createPrinterStatusPill" in app_js
    assert "preform-printer-table" in styles_css
    assert "preform-printer-status-pill" in styles_css
    assert "preform-printer-card" not in styles_css
```

- [ ] **Step 2: Run frontend static test and verify it fails**

Run:

```bash
pytest tests/test_frontend_static.py::test_setup_center_displays_local_printer_status -v
```

Expected: failure because `createPrinterStatusPill`, `preform-printer-table`, and `preform-printer-status-pill` do not exist yet, and `preform-printer-card` still exists.

- [ ] **Step 3: Replace material and status helpers in JavaScript**

In `app/static/app.js`, replace `formatPrinterMaterial` and `formatPrinterStatus` with:

```javascript
function formatPrinterMaterial(printer) {
    const materialName = printer.material_name
        || printer.metadata?.material_name
        || printer.metadata?.tank_material_name
        || printer.metadata?.resin_name
        || printer.metadata?.material
        || printer.metadata?.resin;
    const materialCode = printer.material_code
        || printer.metadata?.material_code
        || printer.metadata?.tank_material_code;
    return {
        label: materialName || materialCode || "-",
        code: materialCode || "",
    };
}

function formatPrinterStatus(printer) {
    return printer.status || printer.metadata?.availability || printer.metadata?.state || "Unknown";
}

function getPrinterStatusTone(status) {
    const normalized = String(status || "").toLowerCase();
    if (normalized.includes("ready") && !normalized.includes("not ready")) {
        return "ready";
    }
    if (
        normalized.includes("not ready")
        || normalized.includes("offline")
        || normalized.includes("error")
        || normalized.includes("failed")
    ) {
        return "blocked";
    }
    return "unknown";
}

function createPrinterStatusPill(status) {
    const pill = document.createElement("span");
    pill.className = `preform-printer-status-pill preform-printer-status-${getPrinterStatusTone(status)}`;
    pill.textContent = status;
    return pill;
}
```

- [ ] **Step 4: Replace card rendering with table rendering**

In `app/static/app.js`, replace the non-empty branch of `renderPreformPrinters` starting at `elements.preformPrinterList.className = "preform-printer-list";` through the end of the `payload.printers.forEach` block with:

```javascript
    elements.preformPrinterList.className = "preform-printer-list";
    elements.preformPrinterList.innerHTML = "";

    const table = document.createElement("table");
    table.className = "preform-printer-table";

    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    ["Printer", "Model", "Status", "Material"].forEach((label) => {
        const th = document.createElement("th");
        th.scope = "col";
        th.textContent = label;
        headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    payload.printers.forEach((printer) => {
        const row = document.createElement("tr");

        const nameCell = document.createElement("td");
        nameCell.className = "preform-printer-name-cell";
        nameCell.textContent = printer.name || "Unnamed printer";
        row.appendChild(nameCell);

        const modelCell = document.createElement("td");
        modelCell.textContent = printer.model || "-";
        row.appendChild(modelCell);

        const statusCell = document.createElement("td");
        statusCell.appendChild(createPrinterStatusPill(formatPrinterStatus(printer)));
        row.appendChild(statusCell);

        const material = formatPrinterMaterial(printer);
        const materialCell = document.createElement("td");
        materialCell.textContent = material.label;
        if (material.code && material.code !== material.label) {
            materialCell.title = material.code;
        }
        row.appendChild(materialCell);

        tbody.appendChild(row);
    });
    table.appendChild(tbody);
    elements.preformPrinterList.appendChild(table);
```

- [ ] **Step 5: Replace printer card CSS with table CSS**

In `app/static/styles.css`, replace the existing `.preform-printer-list`, `.preform-printer-card`, and related card rules with:

```css
.preform-printer-list {
    overflow-x: auto;
}

.preform-printer-list-empty {
    display: block;
    padding: 16px;
    border: 1px dashed var(--line);
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.72);
    color: var(--muted);
    font-family: var(--font-ui);
    font-size: 0.88rem;
}

.preform-printer-table {
    width: 100%;
    min-width: 620px;
    border-collapse: separate;
    border-spacing: 0;
    overflow: hidden;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.9);
}

.preform-printer-table th,
.preform-printer-table td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--line);
    text-align: left;
    vertical-align: middle;
}

.preform-printer-table th {
    background: rgba(247, 246, 242, 0.88);
    color: var(--muted);
    font-family: var(--font-ui);
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
}

.preform-printer-table td {
    font-size: 0.86rem;
}

.preform-printer-table tbody tr:last-child td {
    border-bottom: 0;
}

.preform-printer-name-cell {
    font-family: var(--font-ui);
    font-weight: 700;
}

.preform-printer-status-pill {
    display: inline-flex;
    align-items: center;
    min-height: 24px;
    padding: 3px 8px;
    border-radius: 999px;
    font-family: var(--font-ui);
    font-size: 0.76rem;
    font-weight: 700;
    line-height: 1;
    white-space: nowrap;
}

.preform-printer-status-ready {
    background: rgba(22, 121, 76, 0.1);
    color: #16794c;
}

.preform-printer-status-blocked {
    background: rgba(154, 52, 18, 0.1);
    color: #9a3412;
}

.preform-printer-status-unknown {
    background: rgba(96, 89, 80, 0.12);
    color: var(--muted);
}
```

- [ ] **Step 6: Run frontend static test and verify it passes**

Run:

```bash
pytest tests/test_frontend_static.py::test_setup_center_displays_local_printer_status -v
```

Expected: the test passes.

- [ ] **Step 7: Commit table UI**

Run:

```bash
git add app/static/app.js app/static/styles.css tests/test_frontend_static.py
git commit -m "Make local printers easier to scan" -m "The setup center printer panel is a read-only fleet status surface, so a compact table fits the workflow better than repeated cards. The renderer now uses the explicit material_name field first and keeps raw material codes out of the normal happy path.

Constraint: This panel must remain quick status visibility, not dispatch control.
Rejected: Keep the card grid | repeated labels reduce scan speed as printer count grows.
Confidence: high
Scope-risk: narrow
Directive: Preserve the loading, unavailable, and empty states when changing this table.
Tested: pytest tests/test_frontend_static.py::test_setup_center_displays_local_printer_status -v"
```

---

### Task 3: Run Focused Regression Verification

**Files:**
- Verify: `tests/test_preform_setup.py`
- Verify: `tests/test_frontend_static.py`

- [ ] **Step 1: Run all affected tests**

Run:

```bash
pytest tests/test_preform_setup.py tests/test_frontend_static.py -v
```

Expected: all tests pass.

- [ ] **Step 2: Inspect changed files**

Run:

```bash
git diff --stat HEAD~2..HEAD
git diff --check HEAD~2..HEAD
```

Expected: changed files are limited to schema/router/frontend/test files for printer status. `git diff --check` reports no whitespace errors.

- [ ] **Step 3: Confirm no unrelated files were staged**

Run:

```bash
git status --short
```

Expected: existing unrelated working tree changes may still appear, but no new uncommitted changes from this plan should remain except intentionally untracked `.superpowers/` companion artifacts.

- [ ] **Step 4: Add a verification commit if Task 3 required fixes**

If Step 1 or Step 2 found a defect and a fix was made, commit only those fix files:

```bash
git add app/schemas.py app/routers/preform_setup.py app/static/app.js app/static/styles.css tests/test_preform_setup.py tests/test_frontend_static.py
git commit -m "Verify printer status table behavior" -m "Focused verification caught and fixed printer status table regressions after the schema and UI changes.

Constraint: Verification must stay scoped to the approved printer status surface.
Confidence: high
Scope-risk: narrow
Tested: pytest tests/test_preform_setup.py tests/test_frontend_static.py -v
Tested: git diff --check HEAD~2..HEAD"
```

If Step 1 and Step 2 pass without fixes, do not create this commit.

---

## Self-Review

Spec coverage:

- Compact status table: Task 2.
- Readable material names as primary display: Task 1 and Task 2.
- Raw material codes separated and retained for fallback/debug context: Task 1.
- Current Form 4B/Form 4BL filtering retained: Task 1 leaves `_is_setup_center_printer` unchanged.
- Loading, unavailable, and empty states retained: Task 2 changes only the non-empty render branch.
- Dispatch controls out of scope: no task adds dispatch behavior.

Completeness scan: every task includes exact files, commands, expected results, and concrete code snippets.

Type consistency:

- Backend fields are `material_name` and `material_code`.
- Frontend reads `printer.material_name` and `printer.material_code`.
- Compatibility field `material` remains populated from `material_name or material_code`.
