---
name: formflow-release
description: Build, smoke-test, and release the FormFlow Windows EXE. Use when the user asks to create a Windows executable, test the packaged app from dist, prepare a new FormFlow version, update release automation, or publish a GitHub Release artifact.
---

# FormFlow Release

## Overview

Use this skill to produce the one-file Windows EXE from this repository and prepare a versioned release. The canonical build path is `scripts/builders/build_windows_exe.py`, which creates `dist/FormFlow_vX.Y.Z.exe` using `formflow.spec`.

## Workflow

1. Check the worktree before editing or releasing:

```powershell
git status --short
```

2. Run focused packaging tests before building:

```powershell
python -m pytest tests/test_exe_packaging.py tests/test_health_endpoints.py -q
```

3. Build the EXE. Pass `--version X.Y.Z` when preparing a new version:

```powershell
python scripts/builders/build_windows_exe.py --version 0.1.0
```

4. Smoke-test the packaged EXE without opening a browser:

```powershell
$env:FORMFLOW_WEB_PORT = "8765"
$env:FORMFLOW_WEB_OPEN_BROWSER = "0"
$exe = Resolve-Path "dist/FormFlow_v0.1.0.exe"
$p = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden
try {
  $healthy = $false
  for ($i = 0; $i -lt 60; $i++) {
    try {
      $response = Invoke-RestMethod -Uri "http://127.0.0.1:8765/health" -TimeoutSec 2
      if ($response.status -eq "healthy") {
        $healthy = $true
        break
      }
    } catch {
      Start-Sleep -Seconds 1
    }
  }
  if (-not $healthy) {
    throw "EXE did not become healthy on port 8765"
  }
} finally {
  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  Get-Process | Where-Object { $_.Path -eq $exe.Path } | Stop-Process -Force -ErrorAction SilentlyContinue
  Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
  Remove-Item Env:\FORMFLOW_WEB_PORT -ErrorAction SilentlyContinue
  Remove-Item Env:\FORMFLOW_WEB_OPEN_BROWSER -ErrorAction SilentlyContinue
  if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
    throw "Port 8765 was still listening after EXE cleanup"
  }
}
```

5. For release automation, use `.github/workflows/build-windows-exe.yml`. It builds on `windows-latest`, smoke-tests the EXE, uploads the artifact, and creates a GitHub Release on `vX.Y.Z` tags or manual dispatch with `create_release=true`.

6. For tray releases, launch the EXE normally on a Windows desktop and verify:
   - a tray icon appears
   - right-click menu contains Open FormFlow, Server Status, Re-check PreFormServer, Restart FormFlow, View Logs, and Quit
   - no usable PreFormServer turns the icon red after startup
   - a ready live PreFormServer turns the icon green
   - Quit closes the EXE and releases the port

## Release Notes

- Keep `app/version.py` as the source of truth for the executable name.
- Use tag names in `vX.Y.Z` format so the workflow can derive the release version.
- The packaged EXE stores runtime data and output next to the executable unless the operator sets `FORMFLOW_WEB_DATA_DIR` or `FORMFLOW_WEB_OUTPUT_DIR`.
- Before claiming a production-ready dental handoff, also verify live PreFormServer readiness and the relevant print handoff path.
