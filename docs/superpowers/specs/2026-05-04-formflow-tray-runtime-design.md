# FormFlow Tray Runtime Design
**Date:** 2026-05-04
**Status:** Approved

---

## Context

FormFlow currently has a Windows EXE build path that starts the FastAPI app and opens the browser, but it does not yet behave like the proven YF_ERP desktop runtime. YF_ERP uses `run_server_tray.py` as a long-lived Windows tray process: it creates a `pystray` icon, starts the web server in a background thread, exposes right-click actions, shows Windows dialogs, opens the browser, restarts the server, displays status, opens logs, and quits cleanly.

FormFlow should use the same operating model, adapted to its FastAPI + PreFormServer workflow.

---

## Goal

Build a Windows tray runtime for FormFlow so the packaged EXE starts as a desktop app with a right-click tray menu and live green/yellow/red status icon.

---

## Status Model

The tray icon represents the operator-facing readiness of the local workstation.

| Color | Meaning | Source |
| --- | --- | --- |
| Green | FormFlow is running and PreFormServer is usable. | `/health` returns healthy and `/api/preform-setup/status` returns `readiness == "ready"` |
| Yellow | FormFlow is starting, restarting, or actively checking readiness. | Local runtime state before a completed health/readiness probe |
| Red | FormFlow is running, but no usable PreFormServer is available. | `/health` returns healthy and PreForm readiness is anything other than `ready`, or readiness probing fails after the server is reachable |

If FormFlow itself fails to start, the tray should remain red and the status dialog should show the startup error or log path.

---

## Chosen Approach

Use a YF_ERP-style integrated tray runtime in `run_formflow.py`.

The EXE process owns both the tray icon and the FastAPI server. `run_formflow.py` starts uvicorn in a background thread, runs `pystray.Icon(...).run()` on the main thread, polls the local HTTP endpoints, and updates the icon/title/menu state from those results.

This keeps packaging simple: one executable, one runtime process, one place to manage browser launch, logs, restart, and shutdown.

---

## Tray Menu

Right-click menu:

```text
Open FormFlow
Server Status
Re-check PreFormServer
Restart FormFlow
View Logs
---
Quit
```

Behavior:

- `Open FormFlow` opens `http://127.0.0.1:{port}/`.
- `Server Status` shows a Windows dialog with the current FormFlow URL, PreForm readiness, detected PreForm version when available, and log location.
- `Re-check PreFormServer` sets the icon yellow, calls `/api/preform-setup/recheck`, then refreshes status.
- `Restart FormFlow` confirms with the operator, shuts down the current uvicorn server, starts it again, then refreshes status.
- `View Logs` opens the runtime logs directory.
- `Quit` confirms, stops the tray, requests server shutdown, and exits the process.

Left-click/default action should open FormFlow.

---

## Runtime Structure

`run_formflow.py` should be split into small testable units:

| Unit | Responsibility |
| --- | --- |
| Runtime paths | Resolve EXE/dev runtime root, data dir, output dir, log dir |
| Environment setup | Set `FORMFLOW_WEB_*` defaults before importing `app.main` |
| Status model | Convert health/readiness results into `starting`, `ready`, or `error` |
| Icon renderer | Create 64x64 green/yellow/red tray icons with `Pillow` |
| Server manager | Start and stop uvicorn in a background thread |
| Probe client | Poll `/health`, `/health/ready`, and `/api/preform-setup/status` |
| Tray controller | Build pystray menu, update icon/title, handle menu callbacks |
| Dialog helpers | Use Windows `ctypes.MessageBoxW` first, with safe fallback logging |

Do not put business logic in the tray runtime. The tray only reflects backend readiness and calls existing API endpoints.

---

## Packaging

Update PyInstaller packaging to include tray support:

- add `pystray` and `Pillow` to `requirements.txt`
- include hidden imports for `pystray`, `pystray._win32`, `PIL`, `PIL.Image`, and `PIL.ImageDraw`
- set `console=False` in `formflow.spec` for the customer-facing EXE
- keep `runtime_tmpdir=None`
- keep `strip=False` and `upx=False`

The EXE should continue to write runtime data beside the EXE by default unless these environment variables override it:

- `FORMFLOW_WEB_DATA_DIR`
- `FORMFLOW_WEB_OUTPUT_DIR`
- `FORMFLOW_WEB_DATABASE_PATH`

---

## Error Handling

The tray should not crash just because a probe or browser launch fails.

Rules:

- Startup begins yellow.
- If `/health` cannot be reached within the startup timeout, show red and log the failure.
- If `/health` succeeds but PreForm readiness is not `ready`, show red with the exact readiness value in `Server Status`.
- If the PreForm recheck endpoint returns an API error, show red and include the error message in the status dialog.
- If the browser cannot open, log the error and keep the server running.
- If tray creation fails, fall back to starting the FastAPI server with logging rather than exiting before the operator can use the app.

---

## Verification

Required automated checks:

1. Unit tests for status decision logic:
   - startup/checking maps to yellow
   - healthy + PreForm `ready` maps to green
   - healthy + PreForm `not_installed` maps to red
   - healthy + PreForm probe error maps to red
   - FormFlow health failure maps to red

2. Unit tests for runtime path/env setup:
   - packaged/dev runtime defaults set data, output, database, host, and port consistently

3. Packaging smoke test:
   - build `dist/FormFlow_v{version}.exe`
   - launch it with `FORMFLOW_WEB_OPEN_BROWSER=0` and a test port
   - verify `/health` returns `healthy`
   - verify the process is cleaned up by executable path and port

Required manual/live checks:

1. Launch the EXE normally and confirm the tray icon appears.
2. Right-click the tray icon and confirm every menu action is available.
3. With no usable PreFormServer, confirm icon becomes red after startup.
4. With live PreFormServer ready, confirm icon becomes green.
5. Use `Server Status` to confirm it reports URL, PreForm readiness, and version.
6. Use `Quit` and confirm the process exits cleanly.

Per project rule, do not claim production print-handoff completion until live PreFormServer readiness and the task-specific handoff path have been verified.

---

## Out of Scope

- Auto-updater behavior.
- Setup wizard redesign.
- LAN access redesign.
- Signing or installer creation.
- New print-handoff APIs.
