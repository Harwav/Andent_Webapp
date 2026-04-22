# Work Queue Print Handoff UX Design

Date: 2026-04-22
Status: Approved design for UX workflow shaping before backend data-flow changes
Related mockup: `docs/superpowers/mockups/2026-04-22-work-queue-mockup.html`

## Purpose

This design reshapes the operator experience around `Send to Print` so the UI communicates what is happening to files and print jobs more clearly.

The immediate goal is to improve workflow comprehension and queue visibility first. Backend data-flow and persistence changes can follow later, as long as they support this UX contract.

## Design Goals

1. Keep operators anchored in one primary file-level workspace instead of bouncing between multiple similar tabs.
2. Make it obvious which files still need user attention and which files are already being handled by backend print handoff.
3. Show a clear progression from file-level work to job-level print queue tracking.
4. Preserve a file-level trace path after handoff completes.
5. Surface failures quickly and return them to an actionable place.

## Non-Goals

1. Redesign the backend PreFormServer orchestration in this phase.
2. Add deep step-by-step backend logs to the UI in v1 of this UX change.
3. Create a separate fourth queue tab just for processing.
4. Add new progress columns unless the existing table surfaces prove insufficient.

## Current Problem

The current experience makes the print handoff hard to follow:

1. `Send to Print` does not communicate a clear file-level workflow after the click.
2. The user expectation for `Print Queue` is a table with screenshot previews and print details, but the current surface is card-based.
3. The relationship between file-level work, in-progress backend handoff, and final print jobs is not visually explicit enough.

## Recommended UX Model

The app should separate the workflow into three conceptual surfaces:

1. `Work Queue`
2. `Print Queue`
3. `History`

`Work Queue` remains the default working page and stays file-level.
`Print Queue` is job-level only.
`History` is file-level and acts as the audit trail for completed handoff records.

## Approach Options Considered

### Option 1: Keep current tabs and patch behaviors

Keep the current `Active`, `Processed`, and `Print Queue` structure. Fix `Send to Print`, add a success message, and improve `Print Queue`.

Rejected because it still leaves too much ambiguity around where files are during backend handoff.

### Option 2: Merge file-level work into one queue page with a distinct in-progress section

Use one `Work Queue` page with:

1. a top `File Analysis` section for actionable file rows
2. a lower `In Progress` section for rows already being handled

Accepted because it keeps the current mental model familiar while making the system-owned handoff state explicit.

### Option 3: Single table with filter chips only

Use one file-level table with filters like `Ready`, `In Progress`, `Needs Review`, and `All`.

Rejected because it felt too abstract. The approved direction is stronger when the page itself shows a visual section break between user-owned work and system-owned work.

## Work Queue Design

### Overall Structure

`Work Queue` should be a single page with two major section breaks:

1. `File Analysis`
2. `In Progress`

These sections use the same table language and the same columns. The difference is semantic:

1. `File Analysis` means these files may still need user attention.
2. `In Progress` means the backend is already handling these files and the user generally does not need to intervene.

### File Analysis Section

`File Analysis` should stay close to the current `Active` tab behavior and visual structure.

It remains the place where operators:

1. review files
2. resolve `Needs Review` issues
3. confirm files are ready
4. select ready rows
5. click `Send to Print`

Files that fail during handoff should return here.

### In Progress Section

`In Progress` is the lower section on the same page.

Rules:

1. It uses the same columns as `File Analysis`.
2. It is expanded by default.
3. It is read-only.
4. It communicates that these rows are being handled and do not need user attention right now.

The operator should be able to monitor progress there without taking action.

### Empty State

When no files are currently processing, `In Progress` should remain visible with a compact empty-state message such as:

`No files are currently being processed.`

This preserves the page structure and teaches users where that state lives.

## Send To Print Workflow

When the operator clicks `Send to Print`:

1. A short success message should appear.
2. The user should remain on `Work Queue`.
3. Selected files should leave the actionable `File Analysis` area immediately.
4. Those files should appear in the read-only `In Progress` section.

This is an immediate UI transition. The operator should not wait for deep backend completion before seeing that their action worked.

## Status Presentation

The current backend step should be shown directly inside the existing `Status` cell.

Do not add a new progress column for v1.

Approved examples include:

1. `Processing`
2. `Importing`
3. `Layout`
4. `Validating`
5. `Queued`

The status cell may use a stronger chip and subtle motion for active states, plus a short one-line explanation when helpful.

## Handoff Completion Behavior

When a file successfully reaches a created print job:

1. It should briefly show `Queued` in the `In Progress` section.
2. That confirmation should remain visible for about 2 to 3 seconds, or until the app confirms the related `Print Queue` job exists, whichever happens first.
3. After that brief confirmation, the file row should leave `Work Queue`.
4. The row should move into `History`.

This gives the user closure before the row disappears.

## Failure Behavior

If a row fails during handoff:

1. It should leave `In Progress`.
2. It should return to the top of `File Analysis`.
3. Its `Status` should become `Needs Review`.
4. The status cell should include a short reason such as `Validation failed` or `Print handoff failed`.

Failed rows should not go to `History`, and they should not create fake `Print Queue` entries.

## Mixed Results Messaging

If some rows succeed and others fail within the same send action, the message should be truthful and mixed-result aware.

Example:

`2 files moved to In Progress. 1 file needs review.`

The UX should avoid using a pure success message when the outcome is mixed.

## Print Queue Design

`Print Queue` is job-level only.

The approved model is a table, not a card grid.

### Always-Visible Columns

The minimum always-visible columns should be:

1. `Preview`
2. `Job`
3. `Cases`
4. `Status`
5. `Print Details`

`Print Details` can combine printer, material, and layer information to avoid creating a very wide table.

### Screenshot Preview Behavior

If a job exists but its screenshot is not ready:

1. The `Preview` cell should show `Generating preview`.
2. The placeholder should remain visible.
3. It should not be clickable.

When the screenshot becomes available:

1. The placeholder is replaced by the real thumbnail.
2. The thumbnail becomes clickable.
3. Clicking it opens the inline modal with the full-size image.

### Print Queue Help Panel

Add a compact explanation panel at the top of `Print Queue` describing what users should expect after send.

Working concept:

`How Print Handoff Works`

It should explain, briefly:

1. files are sent from `Work Queue`
2. backend handoff runs
3. real jobs appear in `Print Queue`
4. screenshot previews appear when available

## History Design

`History` is file-level, not job-level.

It holds completed or closed handoff records after rows leave `Work Queue`.

Each `History` row should display a linked job id directly in the row.

### Trace-Back Behavior

When the user clicks the linked `Job` id from a `History` row:

1. the app switches to `Print Queue`
2. the matching job row is highlighted

This creates a clean trace path from file record to print job.

## Interaction Summary

Approved operator flow:

1. User reviews files in `File Analysis`.
2. User clicks `Send to Print`.
3. Short success or mixed-result message appears.
4. User remains on `Work Queue`.
5. Successful rows move into read-only `In Progress`.
6. Status cell reflects backend step changes.
7. Failed rows return to the top of `File Analysis`.
8. Successful rows briefly show `Queued`.
9. Successful rows move to `History`.
10. Their related job appears in `Print Queue`.
11. Users can later trace from `History` back to `Print Queue` through the linked job id.

## Information Architecture Rationale

This design intentionally separates responsibility by surface:

1. `Work Queue` = current file work
2. `Print Queue` = live print jobs
3. `History` = completed file-level records

It avoids:

1. forcing users into automatic context switches
2. mixing file rows and job rows in the same view
3. making backend-owned work look like it still needs user action

## Open Implementation Notes

These are implementation-shaping notes, not unresolved UX decisions:

1. The backend will need a file-level in-progress state model that supports stage updates such as `Layout` and `Validating`.
2. The existing job creation and screenshot availability signals will need to map cleanly onto the UI transitions above.
3. `History` will need enough metadata to store and render the linked print job id.
4. `Print Queue` will need a table renderer instead of the current card renderer.

## Testing Shape

When this design is implemented, verification should cover at least:

1. `Send to Print` moves rows from `File Analysis` to `In Progress` immediately.
2. User remains on `Work Queue` after send.
3. `In Progress` is read-only.
4. Status cell updates through active backend stages.
5. Rows briefly show `Queued` before leaving `Work Queue`.
6. Successful rows move to `History`.
7. Failed rows return to the top of `File Analysis`.
8. Mixed-result messages render correctly.
9. `Print Queue` renders as a table.
10. Screenshot placeholder is visible and non-clickable before image availability.
11. Real screenshot thumbnail becomes clickable once available.
12. Clicking a `History` job link switches to `Print Queue` and highlights the matching job.

## Scope Check

This is focused enough for one implementation plan.

The work can be sequenced roughly as:

1. restructure queue information architecture and static rendering
2. add in-progress state transitions and row movement rules
3. convert `Print Queue` to table layout with screenshot behavior
4. add `History` job-link trace flow

## Final Recommendation

Implement the UX exactly in this order:

1. stabilize the `Work Queue` structure first
2. then make `Print Queue` match the approved table behavior
3. then wire `History` trace-back

Do not start by overfitting backend data flow. The UX contract should lead, and the backend should be shaped to support it.
