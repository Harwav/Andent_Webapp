# Andent MVP Local Test Guide

## Environment
- App repo: `/Users/marcus.liang/Documents/FormFlow_Dent`
- macOS PreFormServer install: `~/Library/Application Support/FormFlow Dent/PreFormServer`
- Local API: `http://127.0.0.1:44388/`

## Current Scope
This MVP supports local testing of:
- ortho / implant approval-package preparation
- splint approval-package preparation
- conservative manual-review fallback for unsafe or ambiguous cases

This MVP does not yet auto-process tooth-model cases. Those are expected to fail to manual review.

## Startup
1. Start PreFormServer.
2. Launch FormFlow Dent with `python3 main.py`.
3. In the app, enable `Andent MVP approval mode`.
4. Select an output folder you can inspect easily.
5. Add a folder of STL files and click `Prepare Approval Package`.

## Expected Output
For a successful approval-ready build:
- `<job>.form`
- `<job>_preview.png`

For blocked cases:
- `manual_review_<timestamp>.json`

In Andent mode:
- no printer dispatch should occur

## Test Matrix

### 1. Ortho / Implant Happy Path
Use filenames like:
- `20260409_CASE123_UnsectionedModel_UpperJaw.stl`
- `20260409_CASE123_Antag.stl`

Expected:
- one approval package created
- `.form` file written
- `_preview.png` written
- no printer dispatch

### 2. Splint Happy Path
Use filenames like:
- `CASE777_bitesplint_cad.stl`

Expected:
- one approval package created
- `.form` file written
- `_preview.png` written
- no printer dispatch

### 3. Tooth Safety Gate
Use filenames like:
- `20260409_CASE999_Tooth_46.stl`

Expected:
- no approval package created
- manual review JSON written
- case blocked safely

### 4. Ambiguous Case-ID Guard
Use filenames like:
- `Julie_UpperJaw.stl`
- `PatientX_splint.stl`

Expected:
- manual review JSON written
- file not auto-grouped under an invented case ID

### 5. FPS Mismatch Guard
Run in Andent mode with an `.fps` that does not match the workflow-required scene settings.

Expected:
- no approval package created
- manual review JSON written
- mismatch reason recorded

## Checklist
- [ ] App launches successfully on macOS
- [ ] PreFormServer API responds on `127.0.0.1:44388`
- [ ] `Andent MVP approval mode` is visible and can be enabled
- [ ] Ortho test folder creates `.form`
- [ ] Ortho test folder creates `_preview.png`
- [ ] Splint test folder creates `.form`
- [ ] Splint test folder creates `_preview.png`
- [ ] Tooth case is blocked to manual review
- [ ] Ambiguous filename is blocked to manual review
- [ ] FPS mismatch is blocked to manual review
- [ ] No printer dispatch occurs in Andent mode
- [ ] Manual review JSON is written when expected

## Known Limits
- Tooth-model automation is intentionally disabled pending verified support-touchpoint constraints.
- Live production confidence still requires operator validation with your real dataset and normal `.fps` presets.
