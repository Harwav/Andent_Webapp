# Andent Web Auto Prep Scope Decisions

> **HISTORICAL — Phase 0 decisions locked 2026-04-15. Do not edit.**

## Phase 0 Build-Today Decisions

Date: `2026-04-15`

### Locked Today Scope
- Build `API + a minimal browser upload/classification page`, not API-only.
- Use the existing `formflow_server` FastAPI app and static asset surface.
- Keep the browser page limited to:
  - STL file selection or drag/drop
  - upload submission
  - per-file classification table rendering
  - editable `Model Type` and `Preset` cells or controls

### Deferred Beyond Today
- Durable save of override edits across refresh, restart, or later review.
- Queue/status history beyond the immediate upload result.
- Packing, support generation, `.form` export, screenshot export, and printer dispatch.
- Exception approval workflows beyond displaying `review_required` and `review_reason`.

### Rationale
- The browser page is now part of Phase 0 because it validates the actual operator-facing intake loop instead of only the backend contract.
- Persistent override save is deferred because it expands the domain model and storage work into the next tranche without improving the first-day proof that upload and classification work.

### Working Assumption
- Phase 0 override edits are session-scoped UI/API state only.
- If durable override persistence is later required in the same milestone, that is a scope expansion into the next phase, not a hidden detail of today's slice.
