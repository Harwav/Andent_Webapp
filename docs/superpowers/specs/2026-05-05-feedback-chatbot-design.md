# Feedback Chatbot — Design Spec

**Date:** 2026-05-05
**Status:** Approved

---

## Context

Operators need a way to report bugs and submit feature requests directly from the app. YF_ERP has a full chatbot system; here we need a minimal version — just type + submit → GitHub issue. No AI, no file uploads, no duplicate detection.

---

## UI

**Floating button:**
- Fixed position, bottom-right corner of the page
- Small circular button with a chat icon (+ or speech bubble)
- Visible on all pages

**Chat panel:**
- Opens as a slide-up panel or modal on button click
- Contains:
  1. Type selector: Bug Report | Feature Request (two buttons)
  2. Description textarea (placeholder: "Describe the issue..." or "Describe your idea...")
  3. Submit button
  4. Cancel/close control

**Metadata collected:**
- `page` — current URL path (e.g., `/print-queue`)
- `os` — detected OS (e.g., "Windows 11")
- `browser` — parsed from User-Agent (e.g., "Chrome 124")
- `resolution` — screen width x height (e.g., "1920x1080")

---

## Backend — `POST /api/feedback/submit`

**Request body:**
```json
{
  "type": "bug",          // "bug" | "feature"
  "description": "...",
  "page": "/print-queue"
}
```

**Behavior:**
1. Validate inputs (type must be bug/feature, description required, max 5000 chars)
2. Build issue title: truncated description (max 80 chars)
3. Build issue body:
   ```
   {description}

   ---
   Page: {page}
   OS: {os}
   Browser: {browser}
   Resolution: {resolution}
   ```
4. Apply labels: `bug` or `enhancement`
5. Create issue via GitHub REST API (`POST /repos/Harwav/Andent_Webapp/issues`)
6. Return `{ "issue_url": "https://github.com/Harwav/Andent_Webapp/issues/N" }`

**Error handling:**
- If GitHub API fails → return 500 with error message
- If token missing → return 500 "Feedback system not configured"

---

## Configuration

**`settings.json` (bundled at build time):**
```json
{
  "github_token": "{{GITHUB_TOKEN}}"
}
```

CI build replaces `{{GITHUB_TOKEN}}` with actual token before bundling.

**`app/config.py`** — `github_token: str | None = None` field added to Settings.

---

## Files to Modify

| File | Change |
|------|--------|
| `app/routers/feedback.py` (new) | `POST /api/feedback/submit` endpoint, GitHub API call |
| `app/static/app.js` | Floating button, chat panel, metadata collection |
| `app/static/index.html` | Chat panel markup (hidden by default) |
| `app/static/styles.css` | Chat panel + floating button styling |
| `app/config.py` | Add `github_token: str \| None = None` to Settings |
| `settings.json` | Add `github_token` placeholder |

---

## UX Details

- **Empty description** → disable submit until text entered
- **Submission success** → show issue URL in panel, offer "Submit another" or close
- **Submission failure** → show error message in panel, allow retry
- **Chat panel close** → no confirmation needed (no in-progress state to lose)