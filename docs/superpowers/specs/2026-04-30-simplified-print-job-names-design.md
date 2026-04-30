# Simplified Print Job Names Design

## Goal

New print jobs should use short operational names in the format `YYMMDD_XXXX`, where `XXXX` is a zero-padded sequence for that date.

Operators should still see which cases are included in each print queue job through the existing Cases display. Case IDs remain metadata, not part of the job name.

## Current Behavior

Print job names are generated from the date plus case IDs, for example:

```text
260430_8425435_9690917_8425424_8425442
```

This keeps case context in the artifact name, but it makes job names long, noisy, and hard to scan when many cases are batched into one build.

The print queue already stores `case_ids` on each `PrintJob` and renders them separately in the Cases column and expandable case list.

## Proposed Behavior

Generate new job names as:

```text
260430_0001
260430_0002
260430_0003
```

The sequence is scoped to the job date. Existing jobs for the same date are scanned, and the next unused four-digit suffix is selected.

Existing historical jobs are not renamed. Only newly created print jobs use the simplified format.

## Architecture

The naming change belongs in `app/services/print_queue_service.py`.

`generate_job_name()` should stop deriving the visible name from `case_ids`. The function should still accept the existing `case_ids` argument for call-site compatibility, but the implementation should ignore it for display-name construction.

`_existing_job_names_for_date()` should continue to load same-day names from SQLite. The generator should consider only names that match `YYMMDD_####` when choosing the next sequence, while still avoiding any exact collision with older same-day names.

The `PrintJob` schema should allow the new format. The current pattern already permits `YYMMDD_<token>`, so no schema change is expected unless implementation verification exposes a stricter downstream assertion.

## Data Flow

1. A build manifest is created from selected ready rows.
2. Case IDs are preserved in manifest ordering through `_manifest_case_ids_by_file_order()`.
3. The job name generator chooses the next `YYMMDD_XXXX` value.
4. The job is inserted into `print_jobs` with:
   - `job_name`: short sequence name
   - `case_ids`: ordered case IDs for display and traceability
   - `manifest_json`: full build manifest
5. Output artifacts are written under the short job name:

```text
output/260430_0001/260430_0001.form
output/260430_0001/260430_0001.png
```

## UI Behavior

The Print Queue Job column displays the short job name.

The Cases column and expandable cases list continue to render `job.case_ids`. No case context should be removed from the operator-facing queue.

Status messages can mention the new short job name, but detailed case context should continue to come from `case_ids`.

## Error Handling

If all suffixes from `0001` through `9999` are already used for a date, job creation should fail with a clear runtime error rather than silently generating an unexpected format.

Existing non-sequence names for the same day should not break generation. They should be treated as reserved names for collision avoidance, but they should not affect the numeric sequence unless they match `YYMMDD_####`.

## Testing

Add or update tests to prove:

- Single-case jobs use `YYMMDD_0001`.
- Multiple jobs on the same date increment to `YYMMDD_0002`, `YYMMDD_0003`, and so on.
- Non-sequence historical names for the same date do not determine the next sequence.
- Exact collisions are avoided.
- `case_ids` are still persisted on `PrintJob`.
- Send-to-print tests expect short output paths while still asserting the correct `case_ids`.

Frontend tests do not need large changes unless an existing assertion expects case IDs inside `job_name`.

## Non-Goals

- Renaming existing output folders, `.form` files, screenshots, or historical database rows.
- Changing build grouping, hold/release behavior, or PreFormServer dispatch.
- Removing case IDs from the print queue.
- Adding a new database sequence table.
