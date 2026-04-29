---
name: fix-issues
description: Fix local repo issues with systematic debugging, TDD, and Playwright visual verification. Trigger with "fix issues", "work on issues", "process issues". (project)
allowed-tools: Bash(gh:*), Bash(git:*), Bash(python:*), Bash(pytest:*), Bash(bash:*), Read, Edit, Write, Glob, Grep, TodoWrite, mcp__playwright__browser_navigate, mcp__playwright__browser_take_screenshot, mcp__playwright__browser_snapshot, mcp__playwright__browser_wait_for
---

# Fix Issues

Fix local repo issues with systematic debugging, TDD, and Playwright visual verification. No AI debate — user approves all fix specs.

**Full workflow:** Read the skill guide below.

## Processing Modes

### Single Issue Mode (default)
- Process one issue at a time
- Full attention on complex issues
- Use for: P0 critical bugs, complex implementations

### Batch Mode (parallel)
- Process multiple issues simultaneously
- Batched user approval checkpoints
- Use for: Multiple related fixes, routine bug fixes
- Feature branch per issue: `fix/issue-N`

## 10-Phase Workflow

### Phase 0: Self-Discovered Issue Detection

**Trigger:** User describes a bug they spotted directly (no issue ID).

If no issue ID is cited:
1. Ask user for a one-line description of what they spotted
2. Create issue via `python .fix-issues/scripts/issues.py create "<description>" --priority P1`
3. Show the new issue ID to user and confirm before continuing
4. Treat this issue ID as the issue for all subsequent phases

**Skip this phase** if the user cited an issue ID (e.g. "fix #1", "work on issue 3").

---

### Phase 1: Discovery & Selection

List open issues:
```bash
python .fix-issues/scripts/issues.py list
```

**Filter out already-handled issues:**
- `pending-confirmation` — already fixed, awaiting user confirmation. **Skip these.**
- `confirmed` — verified fixed. **Skip these.**
- `reopened` — fix didn't work. **Include these.**

**ALWAYS ask user which issues to work on.** Present the filtered list and wait for selection:

```
Found 3 open issues:

[1] (P0, reopened) - Print queue screenshot showing placeholder
[2] (P1, open) - Upload timeout too short for large files
[3] (P2, open) - Typo in error message

Which issues would you like to fix?
  - Single issue: "1" or "just #1"
  - Multiple issues: "1, 3" or "batch 1 3"
  - All issues: "all" or "batch all"
```

**For multiple issues:** Create feature branch per issue: `fix/issue-N`

---

### Phase 2: Replication + Systematic Debugging

**Iron Law:** No fix attempt until root cause is confirmed.

For each selected issue:

1. **Reproduce** — get exact steps, document actual vs expected behavior
2. **Trace call path** — read affected code, follow data flow
3. **Git origin** — find when regression was introduced:
   ```bash
   git log --oneline -20 -- <affected_file>
   git blame -L <start_line>,<end_line> <affected_file>
   git show <commit_hash>
   ```
4. **State root cause** — "Bug is caused by X, confirmed by Y"

Document in `qa_archive/YYYYMMDD_issue_N/`:
- `reproduction_steps.md` — exact steps to trigger the bug
- `actual_behavior.md` — what happens vs what should happen
- `git_origin.md` — commit hash, author, date, diff that introduced the bug

⛔ **Gate before advancing:** You must state: "The root cause is X, confirmed by Y." If you cannot, return to Phase 2 and re-investigate.

---

### Phase 3: Systematic Sweep

**Purpose:** Prevent one-off fixes. Once root cause is known, scan entire codebase for the same anti-pattern.

**Steps:**

1. **Extract the anti-pattern** — state it precisely (e.g., "missing null guard before `.count()`", "hardcoded color instead of CSS variable", "untranslated user-visible string")

2. **Codebase-wide search** — grep across all relevant file types:
   ```bash
   grep -rn "<anti_pattern>" --include="*.py" .
   grep -rn "<anti_pattern>" --include="*.html" .
   grep -rn "<anti_pattern>" --include="*.css" --include="*.js" .
   ```

3. **design.md compliance check** — check `docs/design.md` for UI/UX rules. If the anti-pattern or the fix touches UI, verify compliance:
   - Read `docs/design.md`
   - Check if the fix violates any design rules
   - Document violations found

4. **Categorize findings:**
   - ✅ **Same pattern** — identical anti-pattern, fix is mechanical
   - ⚠️ **Related pattern** — similar but needs individual review
   - 🎨 **design.md violation** — violates a rule in `docs/design.md`

5. **Present to user:**
   ```
   🔍 Systematic Sweep — Issue #1 (Print queue screenshot)

   Root anti-pattern: Missing null check on screenshot cache lookup

   Found 3 additional instances:
     ✅ Same pattern (safe to fix together):
       - app/services/print_queue_service.py:142
       - app/services/build_planning.py:89

     ⚠️ Related pattern (review individually):
       - app/services/preform_setup_service.py:201 — different cache structure

     🎨 design.md violations in scope:
       - None found (checked docs/design.md)

   Fix all "same pattern" instances together with #1?
     - "yes all"         — fix all 2 in the same commit
     - "yes, skip X"    — include specific ones
     - "no"             — fix #1 only
   ```

6. **Wait for user selection** before proceeding.

---

### Phase 4: Spec Document

**Purpose:** Document the fix plan for user approval before implementation.

**Spec location:** `.fix-issues/specs/issue_N.md`

**Sections:**
1. Executive Summary
2. Bug Specification (current vs expected)
3. Root Cause Analysis (from Phase 2)
4. Systematic Sweep Results (including design.md compliance)
5. Technical Solution
6. Testing Strategy (TDD — write failing test first)
7. Acceptance Criteria

**User approval gate** — present spec summary, wait for "yes" or feedback.

---

### Phase 5: Implementation (TDD)

For each approved issue:

- **Write failing test first** — regression test that proves the bug exists
- Apply smallest possible fix
- Run tests to verify
- ONE change at a time — no bundled refactoring

**Test location:** `tests/test_issue_N.py` (pytest)

**If fix doesn't make the test pass:**
- < 3 attempts: Return to Phase 2, re-investigate with new information
- ≥ 3 attempts: ⛔ STOP — present findings to user

---

### Phase 6: Visual Verification

**Trigger:** Only runs when the fix touches `app/static/`, `app/templates/`, or any UI-related files.

1. **Detect UI changes** — check modified files. If no UI files changed, skip to Phase 7.

2. **Ensure server is running** (already running on port 8090 per AGENTS.md)

3. **Navigate and capture:**
   - `mcp__playwright__browser_navigate` to the affected page
   - `mcp__playwright__browser_wait_for` — wait for page to fully load
   - `mcp__playwright__browser_take_screenshot` — full page capture
   - Display screenshot to user

4. **Ask for approval:**
   ```
   📸 Visual check — Issue #1 fix

   [screenshot shown]

   Does this look correct?
     - "yes"    — proceed to Phase 7
     - "fix X"  — describe what needs adjusting
   ```

⛔ **Gate on approval** — do NOT proceed to Phase 7 until user confirms.

---

### Phase 7: Verification & Merge

Merge in priority order (P0 → P1 → P2) with **tiered testing**:

```
For each branch in priority order:
  1. git rev-parse HEAD  # save checkpoint
  2. git merge fix/issue-N
  3. pytest tests/ -k "issue_N"  # affected tests only (~30 sec)
  4. If tests fail: rollback, skip this branch
  5. If tests pass: continue to next branch

After ALL merges:
  6. pytest tests/  # full suite once
  7. If tests fail: identify culprit merge, rollback that one only
  8. If tests pass: git push origin main
```

**User options after rollback:**
- "investigate N" - Debug why it broke
- "skip N" - Continue without it
- "abort" - Stop here

---

### Phase 8: GitHub Commit & Label

After all merges complete and pushed:
1. **GitHub commit** — add a comment to each fixed issue:
   ```bash
   gh issue comment N --body "Fixed in $(git rev-parse --short HEAD)

   Commit: $(git log -1 --format='%H')
   Branch: fix/issue-N
   Deployed: pending-confirmation"

   gh issue edit N --add-label status:pending-confirmation
   ```
2. Set local status to `pending-confirmation`:
   ```bash
   python .fix-issues/scripts/issues.py update N --status pending-confirmation
   ```
3. Remind user: "Verify the fix in the running app. Then confirm or reopen via `python .fix-issues/scripts/issues.py update N --status confirmed` (or `reopened`)."

**Status lifecycle:**
```
open → in-progress → pending-confirmation → confirmed
                                          → reopened
```

## Key Rules

- **Iron Law: No fix without confirmed root cause** — Phase 2 must complete before Phase 3 or any code changes
- **Self-discovered bugs get an issue** — Phase 0 creates a traceable issue automatically
- **Pattern analysis is mandatory** — systematic sweep always runs after root cause is found
- **Feature branches** for batch mode: `fix/issue-N`
- **Sequential merging** prevents git conflicts
- **Ask user for clarification** whenever needed
- **GitHub commit after merge** — `git push origin main` + `gh issue comment` + `gh issue edit --add-label status:pending-confirmation`
- **design.md compliance** — all UI/UX changes must check and follow `docs/design.md`
- **Visual sign-off required** — Playwright screenshot approval before merge for UI changes
- **TDD** — write failing regression test before applying fix

## User Approval Checkpoints

| Phase | Checkpoint |
|-------|-----------|
| Phase 0 | Show auto-created issue ID, confirm before continuing |
| Phase 1 | User selects issue(s) |
| Phase 3 | Systematic sweep results — user approves scope |
| Phase 4 | **WAIT for spec approval** |
| Phase 6 | Visual sign-off — screenshot shown, user must confirm |
| Phase 7 | Merge results |
| Phase 8 | GitHub commit + label applied, pending user verification |

## Batch Mode State Tracking

During batch processing, track state in `.fix-issues/batch.json`:

```json
{
  "batch_id": "batch_20260429_143000",
  "issues": [
    {
      "id": 1,
      "priority": "P0",
      "branch": "fix/issue-1",
      "status": "merged"
    }
  ]
}
```

Clean up this file after batch completes.

## Related

- `.fix-issues/scripts/issues.py` — issue CLI tool
- `docs/design.md` — UI/UX compliance rules
