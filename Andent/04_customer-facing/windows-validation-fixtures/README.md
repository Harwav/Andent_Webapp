# Windows Validation Fixtures

These folders are prepared to match the test matrix in `windows-handoff-test-guide.md`.

## Folders
- `01_ortho_happy`
  - `20260409_CASE123_UnsectionedModel_UpperJaw.stl`
  - `20260409_CASE123_Antag.stl`
- `02_splint_happy`
  - `CASE777_bitesplint_cad.stl`
- `03_tooth_guard`
  - `20260409_CASE999_Tooth_46.stl`
- `04_ambiguous_guard`
  - `Julie_UpperJaw.stl`
  - `PatientX_splint.stl`
- `05_fps_mismatch_guard`
  - `20260409_CASE123_UnsectionedModel_UpperJaw.stl`
  - `20260409_CASE123_Antag.stl`
  - `candidate_mismatch_settings.fps`
- `output`
  - Suggested output target for manual validation runs

## Notes
- These files are copied from existing repo sample assets so the next Windows validation pass can start immediately.
- The `candidate_mismatch_settings.fps` file is only a starting point. If it does not trigger the mismatch guard for the current printer/material setup, replace it with another known-mismatch `.fps`.
- Start PreFormServer with `--port 44388` before launching the app.
- Launch the app with `.\venv\Scripts\python.exe main.py`.
