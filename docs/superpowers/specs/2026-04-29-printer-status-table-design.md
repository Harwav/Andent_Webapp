# Printer Status Table Design

## Context

The setup center currently renders discovered local printers as large cards. That card layout is readable for a few devices but becomes inefficient for quick fleet status checks. The material value can also surface raw Formlabs material codes such as `FLBMAM01`, which are API-boundary details rather than operator-readable labels.

The printer section is for quick status visibility only. It should not become a printer targeting or dispatch control.

## Decision

Replace the discovered-printer card grid with a compact status table.

Columns:

- `Printer`
- `Model`
- `Status`
- `Material`

Rows show physical Form 4B and Form 4BL devices only, preserving the current setup-center filtering. Status should be visually prominent with a small tone-coded pill. Ready printers should be easy to identify in one scan, and not-ready or unknown states should remain visible without dominating the panel.

## Material Display

The API should keep readable material names separate from raw material codes:

- `material_name`: operator-readable material label from PreFormServer, shown in the table.
- `material_code`: raw material or tank code from PreFormServer, retained for fallback/debug context.

The frontend should prefer `material_name`. If no readable name is available, it may fall back to `material_code`, but the main happy path should not display codes such as `FLBMAM01`.

## Backend Shape

Extend normalized printer status data so material name and material code are separate fields. Prefer PreFormServer material-name fields over code fields when normalizing devices. Preserve raw device metadata for troubleshooting, as the current route already does.

The route remains read-only and continues to report unavailable discovery states clearly when PreFormServer is not ready or device discovery fails.

## Frontend Shape

Render the printer list as a semantic table within the existing setup panel. Keep the current loading, unavailable, and empty states. The table should be dense, responsive, and stable on smaller widths.

Suggested visual hierarchy:

- Printer name as the strongest text in the row.
- Model as compact secondary text.
- Status pill with ready/not-ready tone.
- Material as readable text, with raw code shown only when no readable name exists.

## Tests

Update coverage to prove:

- The printer API prefers readable material names over material codes.
- The printer API keeps raw material codes available as separate fallback/debug data.
- The frontend renders the printer status table instead of the card grid.
- Existing unavailable and empty states remain intact.

## Out Of Scope

- Printer dispatch controls.
- Printer group routing changes.
- New external dependencies.
- A full printer fleet optimization view.
