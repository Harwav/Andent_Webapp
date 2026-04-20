# Andent MVP Windows Handoff

## Purpose
Use this document in a new Codex window on a Windows machine to continue the MVP validation from the current state.

Recommended opener for the new Codex window:

`Continue from Andent/04_customer-facing/windows-handoff-test-guide.md and help me run the Windows validation.`

## Current Status
- Andent MVP workflow implementation is in place inside the main FormFlow Dent app.
- Conservative safety gates are implemented:
  - ambiguous case IDs fail to manual review
  - missing dimension proof fails to manual review
  - tooth-model workflows fail to manual review
  - `.fps` workflow mismatch fails to manual review
  - multi-model splint batches fail to manual review if any model stays flat or loses supports
- Current automated evidence on the latest branch:
  - `python3 -m unittest tests.test_macos_ui_regressions tests.test_andent_workflow tests.test_processing_controller_regression tests.test_settings_manager_regression tests.test_app_gui_payload_regression tests.test_batch_optimizer_arch`
  - Result: `28 tests ... OK`
- macOS UI rendering appears broken on this specific machine, so Windows is the preferred path for real end-to-end validation.

## Key Files Changed
- `andent_workflow.py`
- `processing_controller.py`
- `api_client.py`
- `app_gui.py`
- `settings_manager.py`
- `gui_theme.py`
- `tests/test_andent_workflow.py`
- `tests/test_processing_controller_regression.py`
- `tests/test_settings_manager_regression.py`
- `tests/test_app_gui_payload_regression.py`
- `tests/test_macos_ui_regressions.py`

## What The MVP Should Do

### Supported
- ortho / implant approval-package preparation
- splint approval-package preparation
- screenshot + `.form` output for approval
- no printer dispatch in Andent mode
- manual-review fallback for unsafe or ambiguous cases

### Intentionally Blocked
- tooth-model auto-preparation
- ambiguous case grouping
- approval-mode scene creation without fit proof
- `.fps` scene settings that conflict with the workflow requirement

## Windows Setup
1. Get the latest repo state onto the Windows machine.
2. Install or confirm Python environment and dependencies for the app.
3. Install or copy a working Windows PreFormServer.
4. Start PreFormServer and confirm the Local API responds on `http://127.0.0.1:44388/`.
5. Launch FormFlow Dent.

## Validated On This Windows Repo Copy
- Python app launch works from the repo virtualenv:
  - `.\venv\Scripts\python.exe main.py`
- The working PreFormServer launch on this machine is:
  - `"$env:APPDATA\FormFlow Dent\PreFormServer\PreFormServer.exe" --port 44388`
- Verified Local API health response on this machine:
  - `{"version":"3.57.2.624"}`
- Prepared validation fixtures are available at:
  - `Andent\04_customer-facing\windows-validation-fixtures\`
- Prepared output folder:
  - `Andent\04_customer-facing\windows-validation-fixtures\output`

## Suggested Commands

### PreFormServer
Run the installed Windows PreFormServer with the required port argument:

```powershell
& "$env:APPDATA\FormFlow Dent\PreFormServer\PreFormServer.exe" --port 44388
```

If you prefer to use the repo copy directly:

```powershell
& ".\PreFormServer\PreFormServer.exe" --port 44388
```

Health check:

```powershell
curl http://127.0.0.1:44388/
```

Expected response includes a version JSON payload.

### App

```powershell
cd <repo-path>\FormFlow_Dent
.\venv\Scripts\python.exe main.py
```

## In-App Test Flow
1. Enable `Andent MVP approval mode`.
2. Set the output folder to an easy-to-check path.
3. For repeatable testing, uncheck `Archive processed STLs` so source splint fixtures stay in place.
4. Add one test folder at a time.
5. Click `Prepare Approval Package`.

## Test Matrix

### 1. Ortho / Implant Happy Path
Prepared folder:
- `Andent\04_customer-facing\windows-validation-fixtures\01_ortho_happy`

Contained files:
- `20260409_CASE123_UnsectionedModel_UpperJaw.stl`
- `20260409_CASE123_Antag.stl`

Expected:
- one approval package created
- `<job>.form`
- `<job>_preview.png`
- no printer dispatch
- no manual review JSON

### 2. Splint Happy Path
Prepared folder:
- `Andent\04_customer-facing\windows-validation-fixtures\02_splint_happy`

Contained file:
- `CASE777_bitesplint_cad.stl`

Expected:
- approval package created
- `.form`
- `_preview.png`
- no printer dispatch

Required settings:
- `Printer`: `Form 4B`
- `Material`: `LT Clear V2`
- `Layer Height`: `0.100 mm (Default settings)`

### 3. Tooth Safety Gate
Prepared folder:
- `Andent\04_customer-facing\windows-validation-fixtures\03_tooth_guard`

Contained file:
- `20260409_CASE999_Tooth_46.stl`

Expected:
- no approval package
- `manual_review_<timestamp>.json`
- case blocked safely

### 4. Ambiguous Case-ID Guard
Prepared folder:
- `Andent\04_customer-facing\windows-validation-fixtures\04_ambiguous_guard`

Contained files:
- `Julie_UpperJaw.stl`
- `PatientX_splint.stl`

Expected:
- manual review JSON
- no invented case grouping

### 5. FPS Mismatch Guard
Prepared folder:
- `Andent\04_customer-facing\windows-validation-fixtures\05_fps_mismatch_guard`

Contained files:
- `20260409_CASE123_UnsectionedModel_UpperJaw.stl`
- `20260409_CASE123_Antag.stl`
- `candidate_mismatch_settings.fps`

Run in Andent mode with the included `.fps` if it mismatches the workflow requirement, or replace it with another known-mismatch `.fps` for your printer/material combination.

Expected:
- no approval package
- manual review JSON
- mismatch reason recorded

## Pass / Fail Checklist
- [ ] App window renders correctly on Windows
- [ ] PreFormServer API responds locally
- [ ] `Andent MVP approval mode` is visible
- [ ] Ortho case creates `.form`
- [ ] Ortho case creates `_preview.png`
- [ ] Splint case creates `.form`
- [ ] Splint case creates `_preview.png`
- [ ] Tooth case is blocked to manual review
- [ ] Ambiguous filename is blocked to manual review
- [ ] FPS mismatch is blocked to manual review
- [ ] No printer dispatch occurs in Andent mode
- [ ] Manual review JSON appears when expected

## What To Report Back
Capture these for the next Codex window:
- whether the app renders correctly
- PreFormServer version
- exact test folder used
- exact files created in the output folder
- any warning or error dialogs
- any log snippet if a run fails

## If The New Codex Window Needs A Short Prompt
Use:

`Continue from Andent/04_customer-facing/windows-handoff-test-guide.md. Help me validate the Andent MVP on this Windows machine, starting with PreFormServer health check and app launch.`
