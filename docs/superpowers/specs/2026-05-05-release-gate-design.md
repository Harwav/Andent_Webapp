# Hard Ship/No-Ship Release Gate Design

> Created: 2026-05-05
> Status: Draft for review
> Scope: Release-confidence test suite for FormFlow / Andent Web

## Goal

Create one hard release gate that fails the release unless the app proves production-critical behavior end to end on this Windows machine. The gate must include real browser automation, live FastAPI runtime behavior, live PreFormServer readiness and virtual/debug dispatch, packaged Windows runtime proof, and a durable evidence bundle.

The release gate is intentionally slower than a normal development test run. It is the final ship/no-ship decision point, not a PR convenience check.

## Release Boundary

The gate proves release readiness through virtual/debug PreForm printers only.

In scope:

- App launch and health.
- Python backend tests.
- TypeScript and Playwright test integrity.
- Browser-driven operator flows in Chromium.
- Live PreFormServer readiness.
- Live virtual/debug PreForm handoff.
- Form 4BL test dataset upload, classification, packing, and dispatch evidence.
- Pack-one-at-a-time dispatch invariants.
- Held-build and busy-lane behavior.
- Packaged Windows runtime smoke and browser flow.
- Evidence capture and final ship/no-ship verdict.

Out of scope:

- Physical printer dispatch.
- Formlabs cloud/printer production status proof.
- Long-term print success rate measurement after physical printing.
- Replacing the faster mocked Playwright tests used during normal development.

## Canonical Dataset

The release dataset is:

```text
C:\Users\Marcus\Desktop\From 4BL Test Data
```

The gate must fail during environment validation if this folder is missing or contains no `.stl` files. At design time it contains 91 STL files. The count is recorded as evidence rather than hardcoded as an invariant, so the gate can detect and report dataset drift instead of silently using stale assumptions.

The dataset stage writes `dataset-manifest.json` with:

- Absolute source path.
- STL count.
- Filename list.
- File sizes.
- SHA256 hashes.
- Total bytes.
- Gate timestamp.
- Git commit.

This folder is the mandatory live release dataset. Small checked-in STL fixtures remain useful for fast tests and targeted regression tests, but they are not sufficient for ship/no-ship release proof.

## Command Surface

Primary command:

```powershell
python scripts/release_gate/run_release_gate.py `
  --test-data-dir "C:\Users\Marcus\Desktop\From 4BL Test Data" `
  --preform-url "http://127.0.0.1:44388"
```

Useful flags:

```powershell
--headed
--skip-package-build
--evidence-dir docs/02_planning/98_VerificationArtifacts/pre_release_YYYYMMDD_HHMMSS
```

Environment override:

```powershell
$env:FORMFLOW_RELEASE_TEST_DATA_DIR = "C:\Users\Marcus\Desktop\From 4BL Test Data"
```

Python should own orchestration because the gate coordinates Python tests, app runtime, SQLite state, packaging, PreForm probing, and evidence generation. NPM scripts may call the Python harness for convenience.

## Stage Model

The release gate runs these stages in order:

```text
release-gate
  1. environment
  2. static
  3. backend
  4. browser-mocked
  5. browser-live-app
  6. live-preform-virtual
  7. packaged-runtime
  8. evidence-verdict
```

Any failed stage fails the release. The harness may stop at the first failure by default, but it must preserve logs and write a failing verdict. A future `--continue-on-failure` flag may run later independent stages for diagnostic evidence, but it must still produce `SHIP: no`.

## Stage Details

### 1. Environment

Fail fast unless the machine can produce valid release evidence.

Required checks:

- Python is available.
- Node and npm are available.
- Playwright Chromium is installed.
- The FastAPI app imports.
- PreFormServer responds at the configured URL.
- `/api/preform-setup/status` or an equivalent app probe can report readiness once the app is running.
- The canonical dataset exists and has STL files.
- The evidence directory is unique for this run.
- Git branch, commit, dirty status, and command line are recorded.
- Dispatch mode is virtual/debug, not physical.

Artifacts:

- `environment.json`
- `dataset-manifest.json`
- `git-status.txt`
- `preform-status.json`

### 2. Static

Catch broken code and broken release harness wiring before expensive live work.

Required checks:

- Python compile/import smoke for `app`, `core`, `desktop`, and release scripts.
- TypeScript compile for Playwright and release-gate files.
- Release-gate helper imports resolve.
- Package scripts point to existing files.

Artifacts:

- `static.json`
- `python-compile.log`
- `tsc.log`

### 3. Backend

Run the full Python suite as a release blocker:

```powershell
python -m pytest tests/ -q
```

The final verdict must call out failures in these high-risk areas separately:

- Upload and classification.
- Build planning and packing.
- Pack-one-at-a-time dispatch.
- Busy-lane and held-build invariants.
- PreForm client contract.
- Print queue persistence.
- Release-now behavior.
- Tray runtime helpers.
- Packaging helpers.

Artifacts:

- `pytest.log`
- `backend.json`

### 4. Browser Mocked

Run deterministic Chromium tests where backend APIs are mocked with Playwright routes.

Required scenarios:

- Home page boots.
- Row selection selects whole cases correctly.
- Bulk model, preset, and printer edits post expected payloads.
- Duplicate approval flow.
- Send-to-print button enablement and counts.
- Undo removal.
- Polling pause, resume, and update behavior.
- Legend filters.
- Preview modal.
- Stable automation hooks.

Artifacts:

- `browser-mocked.json`
- Playwright traces, screenshots, and videos on failure.

### 5. Browser Live App

Launch the real FastAPI app with isolated SQLite and data directories, then drive Chromium through a normal operator flow.

Required scenario:

1. Open the app.
2. Upload the canonical Form 4BL dataset.
3. Wait for classification to settle.
4. Record Ready, Check, Needs Review, Duplicate, and error counts.
5. Change at least one model type or preset when a safe editable row exists.
6. Select same-case rows.
7. Send eligible rows to print in virtual/debug mode.
8. Verify rows move from Active to In Progress or History.
9. Reload the browser and verify state persists.
10. Restart the app and verify SQLite-backed state persists.

Artifacts:

- `classification-summary.json`
- `browser-live-app.json`
- `app.log`
- Selected success screenshots.
- Playwright failure traces, screenshots, and videos.

### 6. Live PreForm Virtual

This is the core ship/no-ship proof. The stage must use live PreFormServer, but only virtual/debug printer targets.

Required scenario:

1. Confirm live PreFormServer readiness.
2. Confirm the selected dispatch target is virtual/debug.
3. Upload known same-case upper/lower fixtures and the canonical dataset as configured by the scenario.
4. Send rows to virtual/debug PreForm target.
5. Verify a `print_jobs` database row is created.
6. Verify persisted manifest JSON contains case IDs, preset names, compatibility key, import groups, and per-file PreForm hints.
7. Verify the live PreForm scene exists.
8. Verify app scene/job evidence matches live PreForm evidence.
9. Verify no physical printer target was used.

Pack-one-at-a-time invariant scenarios:

- Overflow pool creates multiple queued virtual jobs sequentially when each accepted tray is above target.
- Overflow plus sparse final remainder creates at most one held job for the lane.
- Busy lane creates one held job for the remaining pool, not one held job per preplanned manifest.
- Existing held job plus newly sent compatible rows replans into one replacement held or queued outcome.
- After cutoff, sparse final tray queues instead of holding.

Artifacts:

- `live-virtual-handoff-summary.json`
- `packing-summary.json`
- `print-job-evidence.json`
- `manifest-evidence.json`
- `preform-scene-evidence.json`
- `no-physical-dispatch.json`

### 7. Packaged Runtime

The shipped Windows path must be verified, not only the development server.

Required checks:

- Build or use the current packaged EXE.
- Launch packaged runtime with isolated app data.
- Verify health and readiness.
- Verify browser URL is reachable.
- Run browser smoke against the packaged runtime.
- Run one upload/classification flow against the packaged runtime.
- Confirm runtime logs are written.
- Confirm no startup traceback occurred.

Artifacts:

- `packaged-runtime.json`
- `packaged-runtime.log`
- `packaged-browser-smoke.json`

### 8. Evidence Verdict

The gate ends by generating:

- `release-gate.json`
- `verdict.md`

Every stage writes a JSON record:

```json
{
  "stage": "live-preform-virtual",
  "status": "pass",
  "duration_seconds": 84.2,
  "command": "...",
  "artifacts": ["preform-status.json", "print-job-evidence.json"],
  "notes": []
}
```

`verdict.md` must include:

- `SHIP: yes` or `SHIP: no`.
- Stage summary table.
- PreFormServer readiness and version evidence.
- Dataset path and STL count.
- Browser evidence summary.
- Live virtual dispatch evidence summary.
- Packaged runtime evidence summary.
- Explicit physical-dispatch guard result.
- Known gaps and residual risks.

The release is green only when `verdict.md` says `SHIP: yes` and every required stage has `status: pass`.

## No Physical Dispatch Guard

The release gate must fail if the release run selects, permits, or uses physical-printer dispatch. The mere presence of physical devices in a PreForm device list is not a failure when the app is configured for virtual/debug dispatch and the selected target is verified as virtual/debug.

Required guardrails:

- Harness sets the app to virtual/debug dispatch mode.
- Browser tests select only virtual/debug targets.
- Tests fail if selected device metadata does not identify a virtual/debug target.
- Database evidence records `printer_device_id` and `printer_device_name`.
- PreForm evidence records target scene/job metadata.
- `no-physical-dispatch.json` explicitly records the evaluated target and result.
- Verdict fails if the selected target, DB rows, app response payloads, PreForm evidence, or logs indicate physical dispatch was selected, permitted, or used.

## Timeout Policy

Hard stage timeouts prevent a release gate from hanging indefinitely:

| Stage | Timeout |
| --- | ---: |
| environment | 2 minutes |
| static | 3 minutes |
| backend | 10 minutes |
| browser-mocked | 5 minutes |
| browser-live-app | 8 minutes |
| live-preform-virtual | 20 minutes |
| packaged-runtime | 10 minutes |
| evidence-verdict | 1 minute |

A timeout is a release failure. The harness must preserve partial logs and evidence.

## Implementation Components

Expected new or updated files:

```text
scripts/release_gate/run_release_gate.py
scripts/release_gate/stages.py
scripts/release_gate/evidence.py
scripts/release_gate/preform_probe.py
scripts/release_gate/verdict.py
tests/release_gate/live_virtual_handoff.spec.ts
tests/release_gate/live_pack_invariants.spec.ts
tests/release_gate/packaged_runtime.spec.ts
tests/release_gate/helpers/page.ts
tests/release_gate/helpers/runtime.ts
package.json
README.md
```

The harness owns stage orchestration, subprocess execution, evidence directory lifecycle, timeout handling, PreForm readiness probing, and verdict generation.

Playwright owns browser/operator behavior, traces, videos, screenshots, and click-through flows.

Pytest owns service behavior, database invariants, PreForm client contract, pack-one-at-a-time invariants, and packaging helper checks.

## Acceptance Criteria

The release gate is complete when:

- One command runs all required stages.
- Missing PreFormServer fails the gate.
- Missing canonical dataset fails the gate.
- Browser automation launches Chromium and clicks through real operator flows.
- The canonical dataset is uploaded through the browser in the live app path.
- Live virtual PreForm dispatch produces database, manifest, and scene evidence.
- Physical dispatch is explicitly guarded and fails the gate if detected.
- Pack-one-at-a-time invariants are included in backend and live evidence.
- Packaged runtime is tested.
- `release-gate.json` and `verdict.md` are generated on success and failure.
- A passing run states `SHIP: yes`; any failed required evidence states `SHIP: no`.

## Risks

| Risk | Impact | Handling |
| --- | --- | --- |
| PreFormServer hangs during import/layout | Gate blocks indefinitely without protection | Per-stage timeout, logs, preserved partial evidence |
| Dataset changes silently | Release comparisons become confusing | Dataset manifest with hashes and counts |
| Virtual/debug device naming changes | False failure or unsafe selection | Match through explicit metadata where possible and record evidence |
| Full 91-file browser upload is slow | Gate duration grows | Accept for hard release gate; keep fast fixtures for development tests |
| Packaged EXE build is slow | Release gate becomes expensive | Allow `--skip-package-build` only when using a recorded current package artifact |
| Existing mocked Playwright tests hide backend bugs | False confidence if used alone | Live app and live PreForm stages are required |

## User Decisions Captured

- Gate type: hard ship/no-ship release gate.
- Live handoff boundary: virtual/debug PreForm printers only.
- Canonical test dataset: `C:\Users\Marcus\Desktop\From 4BL Test Data`.
