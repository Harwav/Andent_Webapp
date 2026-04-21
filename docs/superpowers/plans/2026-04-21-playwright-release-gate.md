# Playwright Release Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a release-blocking Playwright suite that simulates operator behavior in the browser, verifies real build-manifest handoff to local PreFormServer, and blocks release on the four approved scenarios.

**Architecture:** The implementation keeps the existing FastAPI app as the product under test and adds a separate Playwright workspace under `tests/release_gate/`. A thin TypeScript runtime layer will start two app instances, while small Python helper scripts will verify SQLite handoff records, persisted build-manifest metadata, and direct PreFormServer scene existence without adding extra Node dependencies beyond Playwright itself.

**Tech Stack:** FastAPI, Python 3.9+, SQLite, Playwright, TypeScript, Node.js, pytest

---

## Resume Status

Last updated: 2026-04-21 after commit `c5a9168`

Execution workspace:
- Current checkout: `D:\Marcus\Desktop\Andent_Webapp`
- Branch: `main`

Completed so far:
- The design was updated and pushed in `c5a9168` to reflect the implemented Form 4BL build-manifest handoff contract.
- No Playwright release-gate implementation files are present in the current checkout.

In progress:
- Plan realignment is in progress because the previous resume note referenced a missing worktree and commits not reachable from this repository.

Next exact step:
1. Treat the old worktree state as unavailable unless it is recovered externally.
2. Rebuild from Task 1 in this checkout or a fresh worktree created from current `main`.
3. Keep the first release gate limited to the four approved scenarios while folding build-manifest proof into the happy paths.

Current worktree note:
- Current `main` contains the Form 4BL build-manifest implementation and updated design.
- The release-gate implementation must assert persisted `print_jobs` manifest fields: `case_ids`, `preset_names_json`, `compatibility_key`, and `manifest_json`.

---

## File Structure

### Existing files to modify

- Modify: `app/static/app.js`
  - Add stable browser test hooks for rows and bulk actions.
  - Fix preset option handling so UI edits use real preset labels instead of raw model labels.
- Modify: `app/database.py`
  - Normalize manual model/preset overrides so persisted preset values remain compatible with PreForm handoff.
- Modify: `.gitignore`
  - Ignore Playwright artifacts while keeping the committed fixture files.
- Modify: `README.md`
  - Add a short release-gate run section after the implementation is working.

### New Node / Playwright files

- Create: `package.json`
  - Playwright workspace and release-gate scripts.
- Create: `tsconfig.json`
  - TypeScript compiler configuration for Playwright tests.
- Create: `playwright.config.ts`
  - Chromium project, artifact retention, and shared defaults.
- Create: `tests/release_gate/smoke.spec.ts`
  - Small first test to prove Playwright can boot the app.
- Create: `tests/release_gate/ui-hooks.spec.ts`
  - Small browser test proving stable selectors and preset-sync behavior.
- Create: `tests/release_gate/runtime.spec.ts`
  - Runtime smoke test for dual app instances.
- Create: `tests/release_gate/release_gate.spec.ts`
  - The four release-gate scenarios.
- Create: `tests/release_gate/helpers/runtime.ts`
  - Start and stop live/dead-port app instances.
- Create: `tests/release_gate/helpers/fixtures.ts`
  - Shared Playwright test fixtures and typed context.
- Create: `tests/release_gate/helpers/page.ts`
  - Browser helpers for upload, selection, and assertions.
- Create: `scripts/release_gate/run_release_gate.mjs`
  - Wrapper that runs Playwright with JSON output, prints a compact summary, and exits with the same status.

### New Python verification files

- Create: `tests/release_gate/helpers/python/release_gate_verify.py`
  - CLI and functions for PreForm health, SQLite print-job lookup, persisted manifest lookup, and scene verification.
- Create: `tests/test_release_gate_verify.py`
  - pytest coverage for the helper module.
- Create: `tests/test_release_gate_preset_normalization.py`
  - pytest coverage for manual preset normalization in `app/database.py`.

### New fixture files

- Create: `tests/release_gate/fixtures/happy/20260409_CASE123_UnsectionedModel_UpperJaw.stl`
- Create: `tests/release_gate/fixtures/happy/20260409_CASE123_UnsectionedModel_LowerJaw.stl`
- Create: `tests/release_gate/fixtures/manual_edit/20260409_CASE555_Tooth_46.stl`
- Create: `tests/release_gate/fixtures/ambiguous/Julie_UpperJaw.stl`

These four fixture names follow the current classification rules in `core/andent_classification.py`:

- `20260409_CASE123_UnsectionedModel_UpperJaw.stl` and `...LowerJaw.stl` share `CASE123`, contain `unsectionedmodel`, and should classify to the standard model path.
- `20260409_CASE555_Tooth_46.stl` carries a stable case ID and `tooth` keyword, making it deterministic for the manual-edit path.
- `Julie_UpperJaw.stl` looks realistic but has no stable case identifier, so it should remain blocked.

---

### Task 1: Bootstrap The Playwright Workspace

**Files:**
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `playwright.config.ts`
- Create: `tests/release_gate/smoke.spec.ts`
- Modify: `.gitignore`

- [ ] **Step 1: Write the failing Playwright smoke test**

```ts
import { test, expect } from '@playwright/test';

test('home page boots in Chromium', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Active Queue' })).toBeVisible();
  await expect(page.locator('#dropzone')).toBeVisible();
  await expect(page.locator('#status-text')).toHaveText('Queue loaded.');
});
```

- [ ] **Step 2: Run the smoke test to verify the workspace is missing**

Run:

```powershell
npx playwright test tests/release_gate/smoke.spec.ts --project=chromium
```

Expected:
- FAIL with missing Playwright config or missing `@playwright/test`.

- [ ] **Step 3: Write the minimal Playwright workspace**

`package.json`

```json
{
  "name": "andent-web-release-gate",
  "private": true,
  "type": "module",
  "scripts": {
    "test:release-gate": "playwright test tests/release_gate/smoke.spec.ts --project=chromium",
    "test:release-gate:headed": "playwright test tests/release_gate/smoke.spec.ts --project=chromium --headed"
  },
  "devDependencies": {
    "@playwright/test": "^1.52.0",
    "@types/node": "^22.15.3",
    "typescript": "^5.8.3"
  }
}
```

`tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "types": ["node", "@playwright/test"]
  },
  "include": ["playwright.config.ts", "tests/release_gate/**/*.ts", "scripts/release_gate/**/*.mjs"]
}
```

`playwright.config.ts`

```ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/release_gate',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  outputDir: 'test-results/playwright',
  use: {
    baseURL: 'http://127.0.0.1:8090',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: 'python -m uvicorn app.main:app --host 127.0.0.1 --port 8090',
    url: 'http://127.0.0.1:8090/health',
    reuseExistingServer: false,
    timeout: 60_000,
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
      },
    },
  ],
});
```

Add to `.gitignore`

```gitignore
playwright-report/
test-results/playwright/
```

- [ ] **Step 4: Install the toolchain and rerun the smoke test**

Run:

```powershell
npm install
npx playwright install chromium
npx playwright test tests/release_gate/smoke.spec.ts --project=chromium
```

Expected:
- PASS with `1 passed`.

- [ ] **Step 5: Commit**

```powershell
@"
Bootstrap Playwright tooling for the release gate

Constraint: Repo currently has no Node or browser-test workspace
Confidence: high
Scope-risk: narrow
Directive: Keep Playwright isolated under tests/release_gate and do not couple it to pytest defaults
Tested: npx playwright test tests/release_gate/smoke.spec.ts --project=chromium
Not-tested: Dual-app runtime and live PreFormServer verification
"@ | git commit -F -
```

### Task 2: Normalize Manual Preset Persistence For Editable Rows

**Files:**
- Create: `tests/test_release_gate_preset_normalization.py`
- Modify: `app/database.py`

- [ ] **Step 1: Write the failing pytest coverage for manual preset normalization**

```python
from pathlib import Path

from app.config import build_settings
from app.database import init_db, persist_upload_session, update_upload_row, bulk_update_upload_rows


def _build_settings(tmp_path):
    data_dir = tmp_path / "data"
    settings = build_settings(data_dir=data_dir, database_path=data_dir / "andent_web.db")
    init_db(settings)
    return settings


def _seed_row(settings, file_name: str, *, model_type: str, preset: str, confidence: str = "high"):
    stored_path = settings.data_dir / file_name
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    stored_path.write_text("solid fixture\nendsolid fixture\n", encoding="utf-8")
    rows = persist_upload_session(
        settings,
        "session-1",
        [
            {
                "file_name": file_name,
                "stored_path": str(stored_path),
                "content_hash": f"hash-{file_name}",
                "thumbnail_svg": None,
                "case_id": "CASE555",
                "model_type": model_type,
                "preset": preset,
                "confidence": confidence,
                "status": "Ready",
                "dimension_x_mm": None,
                "dimension_y_mm": None,
                "dimension_z_mm": None,
                "volume_ml": None,
                "structure": None,
                "structure_confidence": None,
                "structure_reason": None,
                "structure_metrics_json": None,
                "structure_locked": False,
                "review_required": False,
                "review_reason": None,
                "printer": None,
                "person": None,
            }
        ],
    )
    return rows[0].row_id


def test_update_upload_row_maps_model_label_to_real_preset(tmp_path):
    settings = _build_settings(tmp_path)
    row_id = _seed_row(
        settings,
        "20260409_CASE555_Tooth_46.stl",
        model_type="Tooth",
        preset="Tooth - With Supports",
    )

    updated = update_upload_row(settings, row_id, "Ortho - Solid", "Ortho - Solid")

    assert updated.model_type == "Ortho - Solid"
    assert updated.preset == "Ortho Solid - Flat, No Supports"
    assert updated.status == "Ready"


def test_bulk_update_upload_rows_maps_model_label_to_real_preset(tmp_path):
    settings = _build_settings(tmp_path)
    row_id = _seed_row(
        settings,
        "20260409_CASE555_Tooth_46.stl",
        model_type="Tooth",
        preset="Tooth - With Supports",
    )

    rows = bulk_update_upload_rows(settings, [row_id], "Splint", "Splint")

    assert rows[0].model_type == "Splint"
    assert rows[0].preset == "Splint - Flat, No Supports"
    assert rows[0].status == "Ready"
```

- [ ] **Step 2: Run the new pytest file to verify it fails**

Run:

```powershell
pytest tests/test_release_gate_preset_normalization.py -v
```

Expected:
- FAIL because `preset` is currently persisted as raw model labels such as `Ortho - Solid`.

- [ ] **Step 3: Implement preset normalization in `app/database.py`**

Add this import and helper near the existing classification imports:

```python
from .services.classification import (
    default_preset,
    derive_status,
    generate_thumbnail_svg,
    is_current_thumbnail_svg,
)


def _normalize_manual_preset(model_type: str | None, preset: str | None) -> str | None:
    if preset is None:
        return default_preset(model_type) if model_type else None

    normalized_from_model_label = default_preset(preset)
    if normalized_from_model_label is not None:
        return normalized_from_model_label

    return preset
```

Use it in both `update_upload_row(...)` and `bulk_update_upload_rows(...)` before calling `derive_status(...)`:

```python
        preset = _normalize_manual_preset(model_type, preset)
        status = existing["status"]
        if status not in {"Duplicate", "Submitted", "Printed"}:
            status = derive_status(existing["confidence"], model_type, preset, manual_override=True)
```

and:

```python
            raw_preset = preset if preset is not None else row["preset"]
            next_preset = _normalize_manual_preset(next_model_type, raw_preset)
            next_status = row["status"]
            if next_status not in {"Duplicate", "Submitted", "Printed"}:
                next_status = derive_status(row["confidence"], next_model_type, next_preset, manual_override=True)
```

- [ ] **Step 4: Run the normalization tests**

Run:

```powershell
pytest tests/test_release_gate_preset_normalization.py -v
```

Expected:
- PASS with `2 passed`.

- [ ] **Step 5: Commit**

```powershell
@"
Normalize manual preset persistence for release-gate edits

Constraint: Browser edit flows must persist real preset labels that remain compatible with PreForm handoff
Rejected: Keep raw model labels in the database | breaks preset-hint mapping at the handoff boundary
Confidence: high
Scope-risk: narrow
Directive: Any future editable preset UI must continue to store handoff-compatible preset labels, not display-only model labels
Tested: pytest tests/test_release_gate_preset_normalization.py -v
Not-tested: Browser-level preset edit flow
"@ | git commit -F -
```

### Task 3: Add Stable UI Hooks And Realistic Fixture Files

**Files:**
- Modify: `app/static/app.js`
- Create: `tests/release_gate/ui-hooks.spec.ts`
- Create: `tests/release_gate/fixtures/happy/20260409_CASE123_UnsectionedModel_UpperJaw.stl`
- Create: `tests/release_gate/fixtures/happy/20260409_CASE123_UnsectionedModel_LowerJaw.stl`
- Create: `tests/release_gate/fixtures/manual_edit/20260409_CASE555_Tooth_46.stl`
- Create: `tests/release_gate/fixtures/ambiguous/Julie_UpperJaw.stl`

- [ ] **Step 1: Write the failing Playwright test for selector stability and preset sync**

```ts
import path from 'node:path';
import { test, expect } from '@playwright/test';

test('row hooks and preset sync are stable for browser automation', async ({ page }) => {
  await page.goto('/');

  await page.locator('#file-input').setInputFiles([
    path.resolve('tests/release_gate/fixtures/manual_edit/20260409_CASE555_Tooth_46.stl'),
  ]);

  const row = page.locator('[data-file-name="20260409_CASE555_Tooth_46.stl"]');
  await expect(row).toBeVisible();
  await expect(row.locator('[data-testid="status-chip"]')).toHaveText('Ready');

  await row.locator('[data-testid="model-type-select"]').selectOption('Ortho - Solid');
  await expect(row.locator('[data-testid="preset-select"]')).toHaveValue('Ortho Solid - Flat, No Supports');
});
```

- [ ] **Step 2: Run the test to verify the row hooks do not exist yet**

Run:

```powershell
npx playwright test tests/release_gate/ui-hooks.spec.ts --project=chromium
```

Expected:
- FAIL because the row-level `data-*` hooks do not exist and preset sync still uses the wrong values.

- [ ] **Step 3: Implement row hooks, preset options, and the fixture files**

Add these preset constants near the top of `app/static/app.js`:

```js
const DEFAULT_PRESET_BY_MODEL = {
    "Ortho - Solid": "Ortho Solid - Flat, No Supports",
    "Ortho - Hollow": "Ortho Hollow - Flat, No Supports",
    "Die": "Die - Flat, No Supports",
    "Tooth": "Tooth - With Supports",
    "Splint": "Splint - Flat, No Supports",
};

const PRESET_OPTIONS = Object.values(DEFAULT_PRESET_BY_MODEL);

function getDefaultPreset(modelType) {
    return DEFAULT_PRESET_BY_MODEL[modelType] || "";
}
```

Change `normalizeRow(...)`, `createModelTypeSelect(...)`, and `createPresetSelect(...)`:

```js
function normalizeRow(row) {
    const defaultPreset = getDefaultPreset(row.model_type);
    return {
        ...row,
        row_id: row.row_id,
        preset_overridden: Boolean(row.preset && defaultPreset && row.preset !== defaultPreset),
        is_temp: false,
    };
}

// inside createModelTypeSelect change handler:
row.model_type = event.target.value || null;
if (!row.preset_overridden) {
    row.preset = getDefaultPreset(row.model_type);
}
row.preset_overridden = Boolean(row.preset && row.model_type && row.preset !== getDefaultPreset(row.model_type));

// inside createPresetSelect:
PRESET_OPTIONS.forEach((optionValue) => {
    const option = document.createElement("option");
    option.value = optionValue;
    option.textContent = optionValue;
    option.selected = row.preset === optionValue;
    select.appendChild(option);
});
```

Add test hooks during row rendering and bulk-action rendering:

```js
tr.dataset.rowId = String(row.row_id ?? "");
tr.dataset.fileName = row.file_name;
tr.dataset.caseId = row.case_id || "";
tr.dataset.rowStatus = getRowStatus(row);

checkbox.dataset.testid = "row-select";
select.dataset.testid = "model-type-select";
select.dataset.testid = "preset-select";
statusCell.firstChild.dataset.testid = "status-chip";
submitButton.dataset.testid = "send-to-print-button";
```

Add small ASCII STL fixtures. Use this exact shape for each file:

```stl
solid release_gate_fixture
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 20 0 0
      vertex 0 20 0
    endloop
  endfacet
  facet normal 0 0 -1
    outer loop
      vertex 0 0 5
      vertex 0 20 5
      vertex 20 0 5
    endloop
  endfacet
endsolid release_gate_fixture
```

Create the files with these exact names:

```text
tests/release_gate/fixtures/happy/20260409_CASE123_UnsectionedModel_UpperJaw.stl
tests/release_gate/fixtures/happy/20260409_CASE123_UnsectionedModel_LowerJaw.stl
tests/release_gate/fixtures/manual_edit/20260409_CASE555_Tooth_46.stl
tests/release_gate/fixtures/ambiguous/Julie_UpperJaw.stl
```

- [ ] **Step 4: Run the UI-hooks test**

Run:

```powershell
npx playwright test tests/release_gate/ui-hooks.spec.ts --project=chromium
```

Expected:
- PASS with `1 passed`.

- [ ] **Step 5: Commit**

```powershell
@"
Add release-gate UI hooks and realistic browser fixtures

Constraint: Browser automation needs stable selectors and realistic STL names that exercise current classification rules
Confidence: high
Scope-risk: narrow
Directive: Keep release-gate selectors additive and avoid renaming existing UI text just for Playwright
Tested: npx playwright test tests/release_gate/ui-hooks.spec.ts --project=chromium
Not-tested: Dual-app runtime and live PreFormServer verification
"@ | git commit -F -
```

### Task 4: Build Python Verification Helpers For PreForm And SQLite

**Files:**
- Create: `tests/release_gate/helpers/python/release_gate_verify.py`
- Create: `tests/test_release_gate_verify.py`

- [ ] **Step 1: Write the failing pytest coverage for helper functions**

```python
import json
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from release_gate.helpers.python.release_gate_verify import (
    latest_print_job,
    parse_health_response,
)


def test_latest_print_job_returns_manifest_handoff_evidence(tmp_path):
    db_path = tmp_path / "andent_web.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        '''
        CREATE TABLE print_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name TEXT NOT NULL UNIQUE,
            scene_id TEXT,
            print_job_id TEXT,
            status TEXT NOT NULL,
            preset TEXT NOT NULL,
            preset_names_json TEXT,
            compatibility_key TEXT,
            case_ids TEXT,
            manifest_json TEXT,
            created_at TEXT,
            updated_at TEXT,
            screenshot_url TEXT,
            printer_type TEXT,
            resin TEXT,
            layer_height_microns INTEGER,
            estimated_completion TEXT,
            error_message TEXT
        )
        '''
    )
    connection.execute(
        '''
        INSERT INTO print_jobs (
            job_name,
            scene_id,
            print_job_id,
            status,
            preset,
            preset_names_json,
            compatibility_key,
            case_ids,
            manifest_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            "260421-001",
            "scene-123",
            "print-123",
            "Queued",
            "Ortho Solid - Flat, No Supports",
            json.dumps(["Ortho Solid - Flat, No Supports"]),
            "form-4bl|precision-model-resin|100",
            json.dumps(["CASE123"]),
            json.dumps({
                "case_ids": ["CASE123"],
                "preset_names": ["Ortho Solid - Flat, No Supports"],
                "compatibility_key": "form-4bl|precision-model-resin|100",
                "import_groups": [
                    {
                        "preset_name": "Ortho Solid - Flat, No Supports",
                        "preform_hint": "ortho_solid_v1",
                        "row_ids": [1],
                        "files": [
                            {
                                "row_id": 1,
                                "case_id": "CASE123",
                                "file_name": "20260409_CASE123_UnsectionedModel_UpperJaw.stl",
                                "file_path": "data/uploads/session/20260409_CASE123_UnsectionedModel_UpperJaw.stl",
                                "preset_name": "Ortho Solid - Flat, No Supports",
                                "preform_hint": "ortho_solid_v1",
                                "compatibility_key": "form-4bl|precision-model-resin|100",
                                "xy_footprint_estimate": 100.0,
                                "support_inflation_factor": 1.0,
                                "order": 0,
                            }
                        ],
                    }
                ],
                "planning_status": "planned",
                "non_plannable_reason": None,
            }),
            "2026-04-21T00:00:00Z",
            "2026-04-21T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()

    job = latest_print_job(db_path)

    assert job["scene_id"] == "scene-123"
    assert job["print_job_id"] == "print-123"
    assert job["case_ids"] == ["CASE123"]
    assert job["preset_names"] == ["Ortho Solid - Flat, No Supports"]
    assert job["compatibility_key"] == "form-4bl|precision-model-resin|100"
    assert job["manifest_json"]["planning_status"] == "planned"
    assert job["manifest_json"]["import_groups"][0]["files"][0]["preform_hint"] == "ortho_solid_v1"


def test_parse_health_response_accepts_preform_version_payload():
    payload = {"version": "3.57.2.624"}
    parsed = parse_health_response(payload)
    assert parsed["ok"] is True
    assert parsed["version"] == "3.57.2.624"
```

- [ ] **Step 2: Run the new helper tests**

Run:

```powershell
pytest tests/test_release_gate_verify.py -v
```

Expected:
- FAIL because the helper module does not exist yet.

- [ ] **Step 3: Implement the helper module**

`tests/release_gate/helpers/python/release_gate_verify.py`

```python
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import requests


def latest_print_job(database_path: Path) -> dict:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM print_jobs ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise LookupError("No print job rows found.")

    case_ids = json.loads(row["case_ids"]) if row["case_ids"] else []
    preset_names = json.loads(row["preset_names_json"]) if row["preset_names_json"] else []
    manifest_json = json.loads(row["manifest_json"]) if row["manifest_json"] else None
    return {
        "job_name": row["job_name"],
        "scene_id": row["scene_id"],
        "print_job_id": row["print_job_id"],
        "status": row["status"],
        "preset": row["preset"],
        "preset_names": preset_names,
        "compatibility_key": row["compatibility_key"],
        "case_ids": case_ids,
        "manifest_json": manifest_json,
    }


def parse_health_response(payload: dict) -> dict:
    version = str(payload.get("version", "")).strip()
    return {"ok": bool(version), "version": version}


def check_preform_health(base_url: str) -> dict:
    response = requests.get(f"{base_url.rstrip('/')}/", timeout=10)
    response.raise_for_status()
    return parse_health_response(response.json())


def check_scene(base_url: str, scene_id: str) -> dict:
    response = requests.get(f"{base_url.rstrip('/')}/scene/{scene_id}", timeout=10)
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    latest = subparsers.add_parser("latest-print-job")
    latest.add_argument("--database-path", required=True)

    health = subparsers.add_parser("preform-health")
    health.add_argument("--base-url", required=True)

    scene = subparsers.add_parser("scene")
    scene.add_argument("--base-url", required=True)
    scene.add_argument("--scene-id", required=True)

    args = parser.parse_args()

    if args.command == "latest-print-job":
        print(json.dumps(latest_print_job(Path(args.database_path))))
    elif args.command == "preform-health":
        print(json.dumps(check_preform_health(args.base_url)))
    else:
        print(json.dumps(check_scene(args.base_url, args.scene_id)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the helper tests**

Run:

```powershell
pytest tests/test_release_gate_verify.py -v
```

Expected:
- PASS with `2 passed`.

- [ ] **Step 5: Commit**

```powershell
@"
Add release-gate verification helpers for SQLite and PreForm

Constraint: The browser suite must verify app-side print records and direct PreForm scene existence without extra Node database dependencies
Confidence: high
Scope-risk: narrow
Directive: Keep verification helpers CLI-friendly so Playwright can shell out to them deterministically
Tested: pytest tests/test_release_gate_verify.py -v
Not-tested: End-to-end usage from the TypeScript runtime
"@ | git commit -F -
```

### Task 5: Build The Dual-App Runtime Harness

**Files:**
- Create: `tests/release_gate/helpers/runtime.ts`
- Create: `tests/release_gate/helpers/fixtures.ts`
- Create: `tests/release_gate/runtime.spec.ts`

- [ ] **Step 1: Write the failing runtime smoke test**

```ts
import { test, expect } from './helpers/fixtures';

test('runtime starts live and dead-port app instances', async ({ request, liveApp, deadApp }) => {
  const liveHealth = await request.get(`${liveApp.baseURL}/health`);
  expect(liveHealth.ok()).toBeTruthy();

  const deadHealth = await request.get(`${deadApp.baseURL}/health`);
  expect(deadHealth.ok()).toBeTruthy();
});
```

- [ ] **Step 2: Run the runtime smoke test**

Run:

```powershell
npx playwright test tests/release_gate/runtime.spec.ts --project=chromium
```

Expected:
- FAIL because the shared fixtures and runtime launcher do not exist.

- [ ] **Step 3: Implement the runtime layer**

`tests/release_gate/helpers/runtime.ts`

```ts
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';

export type AppInstance = {
  baseURL: string;
  dataDir: string;
  databasePath: string;
  preformUrl: string;
  process: ChildProcessWithoutNullStreams;
};

async function waitForHealth(url: string, timeoutMs = 60_000): Promise<void> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for health: ${url}`);
}

export async function startAppInstance(opts: {
  port: number;
  dataDir: string;
  preformUrl: string;
}): Promise<AppInstance> {
  await fs.mkdir(opts.dataDir, { recursive: true });
  const databasePath = path.join(opts.dataDir, 'andent_web.db');
  const child = spawn(
    'python',
    ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(opts.port)],
    {
      cwd: process.cwd(),
      env: {
        ...process.env,
        ANDENT_WEB_DATA_DIR: opts.dataDir,
        ANDENT_WEB_DATABASE_PATH: databasePath,
        PREFORM_SERVER_URL: opts.preformUrl,
      },
      stdio: 'pipe',
    },
  );

  const baseURL = `http://127.0.0.1:${opts.port}`;
  await waitForHealth(`${baseURL}/health`);

  return { baseURL, dataDir: opts.dataDir, databasePath, preformUrl: opts.preformUrl, process: child };
}

export async function stopAppInstance(app: AppInstance): Promise<void> {
  app.process.kill();
}
```

`tests/release_gate/helpers/fixtures.ts`

```ts
import path from 'node:path';
import { test as base } from '@playwright/test';
import { startAppInstance, stopAppInstance, type AppInstance } from './runtime';

export const test = base.extend<{
  liveApp: AppInstance;
  deadApp: AppInstance;
}>({
  liveApp: [async ({}, use) => {
    const app = await startAppInstance({
      port: 8091,
      dataDir: path.resolve('test-results/release-gate/live-app'),
      preformUrl: 'http://127.0.0.1:44388',
    });
    await use(app);
    await stopAppInstance(app);
  }, { scope: 'worker' }],

  deadApp: [async ({}, use) => {
    const app = await startAppInstance({
      port: 8092,
      dataDir: path.resolve('test-results/release-gate/dead-app'),
      preformUrl: 'http://127.0.0.1:59999',
    });
    await use(app);
    await stopAppInstance(app);
  }, { scope: 'worker' }],
});

export { expect } from '@playwright/test';
```

- [ ] **Step 4: Run the runtime smoke test**

Run:

```powershell
npx playwright test tests/release_gate/runtime.spec.ts --project=chromium
```

Expected:
- PASS with `1 passed`.

- [ ] **Step 5: Commit**

```powershell
@"
Add dual-app runtime harness for the release gate

Constraint: The release suite needs one live PreForm app instance and one dead-port failure instance in the same run
Confidence: high
Scope-risk: moderate
Directive: Keep runtime startup logic in helpers/runtime.ts and avoid scattering process management across specs
Tested: npx playwright test tests/release_gate/runtime.spec.ts --project=chromium
Not-tested: Scenario-level live PreForm submissions
"@ | git commit -F -
```

### Task 6: Implement The Straight-Through Same-Case Happy Path

**Files:**
- Create: `tests/release_gate/helpers/page.ts`
- Modify: `tests/release_gate/helpers/fixtures.ts`
- Create: `tests/release_gate/release_gate.spec.ts`

- [ ] **Step 1: Write the failing straight-through scenario**

```ts
import path from 'node:path';
import { test, expect } from './helpers/fixtures';

test('straight-through same-case multi-file handoff reaches live PreForm', async ({ page, liveApp, latestPrintJob, sceneStatus }) => {
  await page.goto(liveApp.baseURL);
  await page.locator('#file-input').setInputFiles([
    path.resolve('tests/release_gate/fixtures/happy/20260409_CASE123_UnsectionedModel_UpperJaw.stl'),
    path.resolve('tests/release_gate/fixtures/happy/20260409_CASE123_UnsectionedModel_LowerJaw.stl'),
  ]);

  const upperRow = page.locator('[data-file-name="20260409_CASE123_UnsectionedModel_UpperJaw.stl"]');
  const lowerRow = page.locator('[data-file-name="20260409_CASE123_UnsectionedModel_LowerJaw.stl"]');

  await expect(upperRow.locator('[data-testid="status-chip"]')).toHaveText('Ready');
  await expect(lowerRow.locator('[data-testid="status-chip"]')).toHaveText('Ready');

  await upperRow.locator('[data-testid="row-select"]').check();
  await page.locator('[data-testid="send-to-print-button"]').click();
  await expect(page.locator('#status-text')).toContainText('Moved 2 row(s) into Processed as Submitted.');

  const job = await latestPrintJob(liveApp.databasePath);
  expect(job.case_ids).toContain('CASE123');
  expect(job.preset_names).toContain('Ortho Solid - Flat, No Supports');
  expect(job.compatibility_key).toBeTruthy();
  expect(job.manifest_json.case_ids).toContain('CASE123');
  expect(job.manifest_json.planning_status).toBe('planned');
  expect(job.manifest_json.import_groups.length).toBeGreaterThan(0);
  const manifestFiles = job.manifest_json.import_groups.flatMap((group: any) => group.files);
  expect(manifestFiles.map((file: any) => file.file_name)).toEqual(expect.arrayContaining([
    '20260409_CASE123_UnsectionedModel_UpperJaw.stl',
    '20260409_CASE123_UnsectionedModel_LowerJaw.stl',
  ]));
  expect(manifestFiles.every((file: any) => Boolean(file.preform_hint))).toBe(true);

  const scene = await sceneStatus(liveApp.preformUrl, job.scene_id);
  expect(scene.scene_id).toBe(job.scene_id);
});
```

- [ ] **Step 2: Run the scenario**

Run:

```powershell
npx playwright test tests/release_gate/release_gate.spec.ts --project=chromium --grep "straight-through"
```

Expected:
- FAIL because the page helpers and Python-wrapper fixtures are not implemented yet.

- [ ] **Step 3: Implement the page helpers and Python wrappers**

Add to `tests/release_gate/helpers/fixtures.ts`:

```ts
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

async function runVerify(args: string[]) {
  const { stdout } = await execFileAsync('python', ['tests/release_gate/helpers/python/release_gate_verify.py', ...args]);
  return JSON.parse(stdout);
}

export const test = base.extend<{
  liveApp: AppInstance;
  deadApp: AppInstance;
  latestPrintJob: (databasePath: string) => Promise<any>;
  sceneStatus: (baseUrl: string, sceneId: string) => Promise<any>;
}>({
  latestPrintJob: async ({}, use) => {
    await use((databasePath) => runVerify(['latest-print-job', '--database-path', databasePath]));
  },
  sceneStatus: async ({}, use) => {
    await use((baseUrl, sceneId) => runVerify(['scene', '--base-url', baseUrl, '--scene-id', sceneId]));
  },
});
```

Add to `tests/release_gate/helpers/page.ts`:

```ts
import { expect, type Page } from '@playwright/test';

export async function waitForRowReady(page: Page, fileName: string): Promise<void> {
  const row = page.locator(`[data-file-name="${fileName}"]`);
  await expect(row).toBeVisible();
  await expect(row.locator('[data-testid="status-chip"]')).toHaveText('Ready');
}
```

- [ ] **Step 4: Run the straight-through scenario again**

Run:

```powershell
npx playwright test tests/release_gate/release_gate.spec.ts --project=chromium --grep "straight-through"
```

Expected:
- PASS with `1 passed`.

- [ ] **Step 5: Commit**

```powershell
@"
Add the straight-through release-gate scenario

Constraint: The first release blocker must prove a same-case multi-file browser submission all the way to persisted build-manifest evidence and live PreForm scene creation
Confidence: medium
Scope-risk: moderate
Directive: Keep scenario helpers small and focused so later scenarios reuse them instead of duplicating browser steps
Tested: npx playwright test tests/release_gate/release_gate.spec.ts --project=chromium --grep "straight-through"
Not-tested: Manual-edit, ambiguous, and offline scenarios
"@ | git commit -F -
```

### Task 7: Implement The Manual-Edit Happy Path

**Files:**
- Modify: `tests/release_gate/release_gate.spec.ts`

- [ ] **Step 1: Write the failing manual-edit scenario**

```ts
test('manual model and preset edits still hand off to live PreForm', async ({ page, liveApp, latestPrintJob, sceneStatus }) => {
  await page.goto(liveApp.baseURL);
  await page.locator('#file-input').setInputFiles([
    path.resolve('tests/release_gate/fixtures/manual_edit/20260409_CASE555_Tooth_46.stl'),
  ]);

  const row = page.locator('[data-file-name="20260409_CASE555_Tooth_46.stl"]');
  await expect(row.locator('[data-testid="status-chip"]')).toHaveText('Ready');

  await row.locator('[data-testid="model-type-select"]').selectOption('Ortho - Solid');
  await row.locator('[data-testid="preset-select"]').selectOption('Splint - Flat, No Supports');
  await expect(row.locator('[data-testid="status-chip"]')).toHaveText('Ready');

  await row.locator('[data-testid="row-select"]').check();
  await page.locator('[data-testid="send-to-print-button"]').click();
  await expect(page.locator('#status-text')).toContainText('Moved 1 row(s) into Processed as Submitted.');

  const job = await latestPrintJob(liveApp.databasePath);
  expect(job.case_ids).toContain('CASE555');
  expect(job.preset).toBe('Splint - Flat, No Supports');
  expect(job.preset_names).toContain('Splint - Flat, No Supports');
  expect(job.manifest_json.case_ids).toContain('CASE555');
  const splintGroup = job.manifest_json.import_groups.find((group: any) => group.preset_name === 'Splint - Flat, No Supports');
  expect(splintGroup).toBeTruthy();
  expect(splintGroup?.preform_hint).toBe('splint_v1');
  expect(splintGroup?.files[0].preform_hint).toBe('splint_v1');

  const scene = await sceneStatus(liveApp.preformUrl, job.scene_id);
  expect(scene.scene_id).toBe(job.scene_id);
});
```

- [ ] **Step 2: Run the scenario**

Run:

```powershell
npx playwright test tests/release_gate/release_gate.spec.ts --project=chromium --grep "manual model and preset edits"
```

Expected:
- FAIL until the new scenario is wired into the shared file and the helpers are reused correctly.

- [ ] **Step 3: Implement the scenario in `tests/release_gate/release_gate.spec.ts`**

Keep both happy-path scenarios in the same file and import `path` at the top:

```ts
import path from 'node:path';
import { test, expect } from './helpers/fixtures';
import { waitForRowReady } from './helpers/page';
```

Use the helper for the first assertion:

```ts
await waitForRowReady(page, '20260409_CASE555_Tooth_46.stl');
const row = page.locator('[data-file-name="20260409_CASE555_Tooth_46.stl"]');
```

- [ ] **Step 4: Run the manual-edit scenario**

Run:

```powershell
npx playwright test tests/release_gate/release_gate.spec.ts --project=chromium --grep "manual model and preset edits"
```

Expected:
- PASS with `1 passed`.

- [ ] **Step 5: Commit**

```powershell
@"
Add the manual-edit release-gate scenario

Constraint: Release gating must prove that operator edits still persist as build-manifest preset evidence and remain compatible with live PreForm handoff
Confidence: medium
Scope-risk: moderate
Directive: Keep the manual-edit path explicit: model change first, then preset override, then submission
Tested: npx playwright test tests/release_gate/release_gate.spec.ts --project=chromium --grep "manual model and preset edits"
Not-tested: Ambiguous and offline scenarios in the full suite
"@ | git commit -F -
```

### Task 8: Implement The Ambiguous-Case Guard

**Files:**
- Modify: `tests/release_gate/release_gate.spec.ts`

- [ ] **Step 1: Write the failing ambiguous-case scenario**

```ts
test('ambiguous case stays blocked in Active and cannot be sent', async ({ page, liveApp }) => {
  await page.goto(liveApp.baseURL);
  await page.locator('#file-input').setInputFiles([
    path.resolve('tests/release_gate/fixtures/ambiguous/Julie_UpperJaw.stl'),
  ]);

  const row = page.locator('[data-file-name="Julie_UpperJaw.stl"]');
  await expect(row).toBeVisible();
  await expect(row.locator('[data-testid="status-chip"]')).toHaveText('Needs Review');

  await row.locator('[data-testid="row-select"]').check();
  await expect(page.locator('[data-testid="send-to-print-button"]')).toHaveCount(0);
});
```

- [ ] **Step 2: Run the scenario**

Run:

```powershell
npx playwright test tests/release_gate/release_gate.spec.ts --project=chromium --grep "ambiguous case stays blocked"
```

Expected:
- FAIL until the scenario exists in the shared spec file.

- [ ] **Step 3: Implement the scenario**

Append the scenario to `tests/release_gate/release_gate.spec.ts` below the two happy paths:

```ts
test('ambiguous case stays blocked in Active and cannot be sent', async ({ page, liveApp }) => {
  await page.goto(liveApp.baseURL);
  await page.locator('#file-input').setInputFiles([
    path.resolve('tests/release_gate/fixtures/ambiguous/Julie_UpperJaw.stl'),
  ]);

  const row = page.locator('[data-file-name="Julie_UpperJaw.stl"]');
  await expect(row.locator('[data-testid="status-chip"]')).toHaveText('Needs Review');
  await row.locator('[data-testid="row-select"]').check();
  await expect(page.locator('[data-testid="send-to-print-button"]')).toHaveCount(0);
});
```

- [ ] **Step 4: Run the ambiguous-case scenario**

Run:

```powershell
npx playwright test tests/release_gate/release_gate.spec.ts --project=chromium --grep "ambiguous case stays blocked"
```

Expected:
- PASS with `1 passed`.

- [ ] **Step 5: Commit**

```powershell
@"
Add the ambiguous-case release gate

Constraint: The release blocker must prove that realistic ambiguous inputs remain blocked in the Active queue
Confidence: high
Scope-risk: narrow
Directive: This scenario must fail if the UI ever exposes Send to Print for a blocked ambiguous row
Tested: npx playwright test tests/release_gate/release_gate.spec.ts --project=chromium --grep "ambiguous case stays blocked"
Not-tested: Offline failure scenario and final summary runner
"@ | git commit -F -
```

### Task 9: Implement The Offline Failure Scenario And Release-Gate Summary Runner

**Files:**
- Modify: `playwright.config.ts`
- Modify: `tests/release_gate/helpers/fixtures.ts`
- Modify: `tests/release_gate/release_gate.spec.ts`
- Create: `scripts/release_gate/run_release_gate.mjs`
- Modify: `README.md`

- [ ] **Step 1: Write the failing offline scenario and runner command**

Add this scenario to `tests/release_gate/release_gate.spec.ts`:

```ts
test('dead-port PreForm configuration surfaces a clean send failure', async ({ page, deadApp }) => {
  await page.goto(deadApp.baseURL);
  await page.locator('#file-input').setInputFiles([
    path.resolve('tests/release_gate/fixtures/happy/20260409_CASE123_UnsectionedModel_UpperJaw.stl'),
  ]);

  const row = page.locator('[data-file-name="20260409_CASE123_UnsectionedModel_UpperJaw.stl"]');
  await expect(row.locator('[data-testid="status-chip"]')).toHaveText('Ready');
  await row.locator('[data-testid="row-select"]').check();
  await page.locator('[data-testid="send-to-print-button"]').click();
  await expect(page.locator('#status-text')).toContainText('Failed to connect to PreFormServer');
  await expect(page.locator('[data-testid="send-to-print-button"]')).toHaveCount(1);
});
```

Add a runner script call to `package.json`:

```json
"test:release-gate": "node scripts/release_gate/run_release_gate.mjs"
```

- [ ] **Step 2: Run the full release-gate command**

Run:

```powershell
npm run test:release-gate
```

Expected:
- FAIL because the summary runner does not exist yet and the offline scenario is not wired into a JSON-report flow.

- [ ] **Step 3: Implement the runner, reporting, and offline scenario**

Update `playwright.config.ts`:

```ts
reporter: [
  ['line'],
  ['json', { outputFile: 'test-results/release-gate/results.json' }],
],
```

Add a manifest-summary helper near the top of `tests/release_gate/release_gate.spec.ts`:

```ts
function manifestSummary(job: any): Record<string, unknown> {
  const importGroups = job.manifest_json?.import_groups ?? [];
  const fileCount = importGroups.reduce((total: number, group: any) => total + (group.files?.length ?? 0), 0);
  return {
    job_name: job.job_name,
    scene_id: job.scene_id,
    print_job_id: job.print_job_id,
    case_ids: job.case_ids,
    preset_names: job.preset_names,
    compatibility_key: job.compatibility_key,
    import_group_count: importGroups.length,
    file_count: fileCount,
  };
}
```

In each happy-path scenario, immediately after manifest assertions pass, add:

```ts
console.log(`[release-gate-manifest] ${JSON.stringify(manifestSummary(job))}`);
```

Create `scripts/release_gate/run_release_gate.mjs`:

```js
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';

const resultsFile = 'test-results/release-gate/results.json';

const exitCode = await new Promise((resolve) => {
  const child = spawn(
    process.platform === 'win32' ? 'npx.cmd' : 'npx',
    ['playwright', 'test', 'tests/release_gate/release_gate.spec.ts', '--project=chromium'],
    { stdio: 'inherit' },
  );
  child.on('exit', (code) => resolve(code ?? 1));
});

const report = JSON.parse(await fs.readFile(resultsFile, 'utf8'));
const specs = report.suites.flatMap((suite) => suite.specs ?? []);
for (const spec of specs) {
  const title = spec.title;
  const tests = spec.tests ?? [];
  for (const item of tests) {
    const result = item.results?.[0];
    console.log(`[release-gate] ${title}: ${result?.status ?? 'unknown'}`);
  }
}

process.exit(exitCode);
```

Add a short README section:

````md
## Release Gate

```bash
npm install
npx playwright install chromium
npm run test:release-gate
```

Prerequisite: a live PreFormServer is reachable at `http://localhost:44388`.
````

- [ ] **Step 4: Run the full release gate**

Run:

```powershell
npm run test:release-gate
```

Expected:
- PASS with all four scenarios green and a printed summary similar to:

```text
[release-gate] straight-through same-case multi-file handoff reaches live PreForm: passed
[release-gate] manual model and preset edits still hand off to live PreForm: passed
[release-gate] ambiguous case stays blocked in Active and cannot be sent: passed
[release-gate] dead-port PreForm configuration surfaces a clean send failure: passed
[release-gate-manifest] {"job_name":"260421-001","scene_id":"...","print_job_id":"...","case_ids":["CASE123"],"preset_names":["Ortho Solid - Flat, No Supports"],"compatibility_key":"form-4bl|precision-model-resin|100","import_group_count":1,"file_count":2}
```

- [ ] **Step 5: Commit**

```powershell
@"
Finish the release-gate suite and summary runner

Constraint: Release decisions need a compact browser-suite summary, not only raw Playwright output
Rejected: Rely only on the default Playwright reporter | too noisy for release sign-off and weak at surfacing the approved four-scenario contract
Confidence: medium
Scope-risk: moderate
Directive: Keep the first release gate limited to the approved four scenarios even if other acceptance ideas are tempting
Tested: npm run test:release-gate
Not-tested: Headed browser mode outside local development
"@ | git commit -F -
```

---

## Self-Review

### Spec coverage

The approved spec requires:

1. Local app plus live PreFormServer, without Formlabs cloud proof.
2. Four scenarios only.
3. Same-case multi-file straight-through happy path.
4. Manual-edit path with model change and explicit preset override.
5. Ambiguous-case guard blocked in `Active`.
6. Dead-port offline failure path.
7. Direct PreForm verification for happy paths.
8. Persisted build-manifest verification for happy paths, including case IDs, preset names, compatibility key, import groups, file records, and PreForm preset hints.
9. Compact reporting with manifest summaries and screenshots on failure.

Plan coverage:

1. Task 1 adds the Playwright workspace.
2. Task 2 fixes preset persistence needed for manual-edit compatibility.
3. Task 3 adds deterministic fixtures and browser hooks.
4. Task 4 adds Python verification helpers for SQLite print-job manifest evidence and PreForm.
5. Task 5 adds the dual-app runtime and PreForm health gate.
6. Tasks 6 and 7 assert persisted manifest evidence inside the two happy paths.
7. Tasks 6 through 9 implement the four scenarios and reporting.

No approved design requirement is left without a task.

### Placeholder scan

No unresolved placeholders remain.

### Type consistency

- Browser runtime types stay in `tests/release_gate/helpers/runtime.ts` and are reused from `helpers/fixtures.ts`.
- Python verification entry points stay in `tests/release_gate/helpers/python/release_gate_verify.py`.
- Release-gate scenarios live in one spec file so shared fixture names and helper signatures stay aligned.
