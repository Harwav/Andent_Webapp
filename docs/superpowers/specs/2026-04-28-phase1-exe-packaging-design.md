# FormFlow — MVP Expansion Design

**Date:** 2026-04-28
**Status:** Approved

---

## Context

FormFlow currently runs from source via `uvicorn app.main:app`. There is no packaging, distribution, or CI/CD infrastructure. The goal is to deliver a standalone Windows executable — double-clickable, system-tray resident, with local data storage — matching the YF_ERP deployment pattern.

---

## Architecture

The packaged EXE is a **single PyInstaller onefile executable** that:

- Extracts to `%TEMP%` on launch
- Starts FastAPI/Uvicorn on port `8090`
- Creates a system tray icon
- Auto-opens the default browser to `http://localhost:8090`

**Data directory:** `%APPDATA%\FormFlow\` (created on first launch)

```
%APPDATA%/FormFlow/
├── config.env          # Runtime configuration (port, LAN settings, PreForm path)
├── data/
│   ├── formflow.sqlite3  # Main SQLite database
│   ├── uploads/        # STL files
│   ├── screenshots/    # Print job screenshots
│   ├── backups/        # Auto-backups of SQLite
│   └── logs/          # App logs
└── PreFormServer/      # PreFormServer installation (if installed via wizard)
```

**LAN access:** When `ALLOW_LAN_ACCESS=true` in `config.env`, Uvicorn binds to `0.0.0.0:8090`. A banner in the UI shows the LAN URL (`http://{local_ip}:8090`).

---

## System Tray

### Icon States

| Color | Meaning |
|-------|---------|
| Green | Running, healthy |
| Yellow | Running, degraded (e.g., PreFormServer not connected) |
| Red | Stopped / error |

### Right-Click Menu

| Menu Item | Action |
|-----------|--------|
| Open FormFlow | Opens `http://localhost:8090` in browser |
| Stop Server | Shuts down uvicorn, exits app |
| Restart Server | Stops and re-starts uvicorn |
| --- | separator |
| Exit | Full shutdown |

### Window Behavior

- Clicking the window close button minimizes to tray instead of exiting
- Tray icon tooltip shows server status

---

## Auto-Start

On first launch, optionally prompt: *"Start with Windows?"* — creates/removes a registry entry at `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

---

## Build Output

```
dist/
└── FormFlow_v{version}.exe   # Single self-contained executable
```

Build script: `scripts/build_exe.py` using PyInstaller.

---

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Packaging | PyInstaller onefile | Simplest single-EXE distribution |
| Tray library | pystray | Cross-platform tray support, Windows-compatible |
| Tray + server | multiprocessing | Uvicorn runs in subprocess, tray in main process |
| Reloader | Disabled | Does not work with PyInstaller |
| Static files | `--add-data` | Bundle app/static, app/routers, core |
| Data path | `platformdirs` | `Path(app_data_dir())` for `%APPDATA%` resolution |
| Config | `config.env` | Environment-var-based, persisted to disk |

---

## Data Directory Initialization

On first launch:

1. Create `%APPDATA%\FormFlow\` if not exists
2. Create subdirectories: `data/`, `data/uploads/`, `data/screenshots/`, `data/backups/`, `data/logs/`
3. Create `config.env` with defaults:
   ```
   PORT=8090
   ALLOW_LAN_ACCESS=true
   PREFORM_PATH=%APPDATA%\FormFlow\PreFormServer
   ```
4. Initialize SQLite at `data/formflow.sqlite3`

---

## LAN Access

When enabled:

1. UI displays a banner: *"Access from other computers: http://{local_ip}:8090"`. The local IP is resolved via `socket.gethostbyname(socket.gethostname())`.
2. Uvicorn binds to `0.0.0.0:8090` instead of `127.0.0.1:8090`.
3. No firewall changes are made automatically — user must open port 8092 on Windows Firewall if needed.

---

## Open Questions / Future

- [ ] Auto-backup schedule for SQLite (e.g., daily at 18:00 or on startup)
- [ ] Version update mechanism (check GitHub Releases, prompt to download)
- [ ] macOS EXE packaging (future phase)

---

## Implementation Steps

1. **Scaffold build script** — `scripts/build_exe.py` with PyInstaller
2. **Add data path abstraction** — `app/data_path.py` using `platformdirs`
3. **Add `config.env` loading** — `app/config.py` reads/writes env file
4. **Wire data directory** — migrate `database.py`, `uploads.py` to use `data_path`
5. **Add tray entry point** — `app/tray.py` wrapping pystray + multiprocessing
6. **Integrate tray into main** — `main.py` starts tray process alongside uvicorn
7. **Add LAN banner** — UI shows LAN URL when `ALLOW_LAN_ACCESS=true`
8. **First EXE build** — verify it runs outside dev environment
9. **Validate full flow** — all verification items pass

---

## Files to Change

| File | Change |
|------|--------|
| `app/config.py` | Add `config.env` read/write support, add `APP_DATA_DIR` |
| `app/database.py` | Change `data/` to `APP_DATA_DIR/data/` |
| `app/routers/uploads.py` | Change upload path to `APP_DATA_DIR/data/uploads/` |
| `app/routers/print_queue.py` | Change screenshot path to `APP_DATA_DIR/data/screenshots/` |
| `app/main.py` | Start tray process, pass `APP_DATA_DIR` to routers |
| `app/static/app.js` | Add LAN URL banner rendering |
| `scripts/build_exe.py` | New — PyInstaller build script |
| `requirements.txt` | Add `pystray`, `Pillow`, `platformdirs`, `pyinstaller` |

---

## Dependencies to Add

```
pystray>=0.19.5
Pillow>=10.0.0
platformdirs>=4.0.0
pyinstaller>=6.0.0
```

---

## Migration Path (Existing Users)

Users upgrading from source-code run:
- First launch of EXE detects no `%APPDATA%\FormFlow\` exists
- Shows one-time dialog: *"Where should data be stored?"*
  - **New location** (default): `%APPDATA%\FormFlow\`
  - **Keep existing**: `<existing source checkout>\data\`
- If user picks existing, symlink or copy old data to new location
- If no existing data, start fresh

---

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Port 8090 already in use | Try 8091, 8092, 8093 — show error after 3 attempts |
| `%APPDATA%\FormFlow\` read-only | Show error dialog, offer to pick alternate location |
| PreFormServer already running | Detect via `localhost:44388` — skip auto-start wizard |
| EXE launched twice | Detect existing tray icon — bring existing window to front, exit new instance |
| No network adapter | Hide LAN banner; tray tooltip shows "localhost only" |
| Antivirus blocks EXE | User must add exception — no workaround in-app |

---

## Verification

- Double-click EXE, verify tray icon appears (green)
- Browser opens to `http://localhost:8090`
- `%APPDATA%\FormFlow\` directory created with correct structure
- Minimize to tray works (close button hides window)
- Tray "Open" re-opens browser
- Tray "Exit" fully terminates the process
- From second machine on LAN: `http://{ip}:8090` loads the UI
- Tray icon color reflects server health state

---

# Phase 2: Feedback Form + GitHub Issue Integration

**Date:** 2026-04-28
**Status:** Draft

---

## Context

FormFlow needs a way for users to report bugs and suggest features. The goal is a simple in-app feedback form that submits directly to GitHub issues — no admin dashboard, no local tracking beyond what's needed to show confirmation to the user.

---

## Feedback Widget

A floating **"Feedback"** button in the bottom-right corner of the UI. Clicking opens a modal form.

**Form fields:**
| Field | Type | Required |
|-------|------|----------|
| Type | Radio: Bug Report / Feature Request | Yes |
| Title | Text input (max 100 chars) | Yes |
| Description | Textarea (max 2000 chars) | Yes |
| Attachments | File upload (images, PDFs, videos — max 10MB each, max 5 files) | No |

**Submission flow:**
1. User fills form → clicks Submit
2. Frontend sends `POST /api/feedback/submit` with form data + files
3. Backend saves files to `feedback_attachments/` in app data dir
4. Backend calls GitHub API → creates issue in FormFlow repo
5. User sees confirmation: *"Feedback submitted! Issue #{number}"* with link to GitHub
6. Option to submit another or close

**Rate limiting:** 20 submissions per user per day (tracked via `user_token` cookie).

---

## Backend Endpoint

```
POST /api/feedback/submit
  body: multipart/form-data
    type: "bug" | "feature"
    title: string
    description: string
    files: File[]

Response 200:
  { "success": true, "issue_number": 123, "issue_url": "https://github.com/..." }

Response 400:
  { "error": "Title and description are required." }

Response 429:
  { "error": "Rate limit exceeded. Try again tomorrow." }
```

New table: `feedback_submissions`
```sql
CREATE TABLE feedback_submissions (
    id INTEGER PRIMARY KEY,
    user_token TEXT NOT NULL,
    type TEXT NOT NULL,          -- 'bug' or 'feature'
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    attachments TEXT,            -- JSON array of {filename, path}
    github_issue_number INTEGER,
    github_issue_url TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## GitHub API Integration

- Uses **Personal Access Token** stored in `config.env` (`GITHUB_TOKEN`)
- Creates issue via `POST /repos/{owner}/{repo}/issues`
- Requires env vars: `GITHUB_TOKEN`, `GITHUB_REPO_OWNER`, `GITHUB_REPO_NAME`
- Issue body includes:
  - Type label: `bug` or `enhancement`
  - Description
  - Attachment filenames (files stored in `%APPDATA%\FormFlow\data\feedback_attachments\`)
  - Submitted-at timestamp
  - User token (anonymized — not real email/name)

**Issue title format:**
- Bug: `[Bug] {user_title}`
- Feature: `[Feature] {user_title}`

---

## Files to Add/Change

| File | Change |
|------|--------|
| `app/routers/feedback.py` | New — submit feedback endpoint |
| `app/services/github_client.py` | New — GitHub API wrapper |
| `app/database.py` | Add `feedback_submissions` table |
| `app/static/app.js` | Add feedback widget + modal |
| `app/static/styles.css` | Add widget + modal styles |
| `requirements.txt` | Add `PyGithub` or use `requests` directly |

---

## Verification

- Submit bug report → GitHub issue created with correct label and body
- Submit feature request → GitHub issue created with `enhancement` label
- Attach image → file saved locally, referenced in issue body
- Rate limit hit → 429 response, error shown to user
- No `GITHUB_TOKEN` → graceful error logged, user sees "Feedback unavailable"
