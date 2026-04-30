# Simplified Print Job Names Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** New print jobs use short daily sequence names like `260430_0001` while the Print Queue continues to show included case IDs through the existing Cases display.

**Architecture:** Keep the change in the print queue service naming layer. Preserve the existing `case_ids` persistence and API shape, and update tests that currently expect case IDs inside `job_name`.

**Tech Stack:** Python 3.9+, FastAPI service layer, SQLite-backed print job records, pytest.

---

## File Structure

- Modify: `app/services/print_queue_service.py`
  - Replace case-ID-derived job name generation with date-scoped sequence generation.
  - Keep `_existing_job_names_for_date()` as the database source of reserved same-day names.
- Modify: `tests/test_integration.py`
  - Replace the generator test that expects case IDs in names with daily sequence tests.
- Modify: `tests/test_preform_handoff.py`
  - Update send-to-print expectations so output paths and PreForm job names use `YYMMDD_XXXX`.
  - Keep assertions proving `case_ids` still persist on jobs and manifests.
- No change expected: `app/static/app.js`
  - Existing print queue rendering already displays `job.case_ids` in the Cases column and expandable list.
- No change expected: `app/schemas.py`
  - Current `PrintJob.job_name` pattern already allows `YYMMDD_0001`.

## Task 1: Lock Daily Sequence Naming With Tests

**Files:**
- Modify: `tests/test_integration.py`
- Test: `tests/test_integration.py`

- [ ] **Step 1: Replace the old case-ID naming test with sequence tests**

Replace `TestFullPrintHandoffFlow.test_job_names_include_case_ids` with:

```python
    def test_job_names_use_daily_sequence(self):
        """Job names should use date prefix plus a daily four-digit sequence."""
        from app.services.print_queue_service import generate_job_name

        date = datetime(2026, 4, 21)

        job1 = generate_job_name(date, ["CASE001"])
        job2 = generate_job_name(
            date,
            ["CASE002", "CASE003"],
            existing_names={"260421_0001"},
        )
        job3 = generate_job_name(
            date,
            ["CASE/004"],
            existing_names={"260421_CASE-OLD"},
        )
        job4 = generate_job_name(
            date,
            [],
            existing_names={"260421_0001", "260421_CASE-OLD", "260421_0003"},
        )

        assert job1 == "260421_0001"
        assert job2 == "260421_0002"
        assert job3 == "260421_0001"
        assert job4 == "260421_0002"

    def test_job_name_sequence_fails_after_daily_limit(self):
        """Job name generation should fail clearly when all daily slots are used."""
        from app.services.print_queue_service import generate_job_name

        date = datetime(2026, 4, 21)
        existing_names = {f"260421_{sequence:04d}" for sequence in range(1, 10000)}

        try:
            generate_job_name(date, ["CASE001"], existing_names=existing_names)
        except RuntimeError as exc:
            assert "Could not generate a unique daily print job name" in str(exc)
        else:
            raise AssertionError("Expected daily sequence exhaustion to raise RuntimeError")
```

- [ ] **Step 2: Run the focused failing tests**

Run:

```powershell
pytest tests/test_integration.py::TestFullPrintHandoffFlow::test_job_names_use_daily_sequence tests/test_integration.py::TestFullPrintHandoffFlow::test_job_name_sequence_fails_after_daily_limit -v
```

Expected: `test_job_names_use_daily_sequence` fails because `generate_job_name()` still returns case-ID-based names.

- [ ] **Step 3: Commit the failing tests**

Run:

```powershell
git add tests/test_integration.py
git commit -m "Specify daily sequence print job names" -m "Print job names are becoming operational identifiers, so tests now lock the YYMMDD_XXXX contract before changing the service implementation.

Constraint: Case traceability remains in PrintJob.case_ids, not job_name
Rejected: Truncated case IDs in job_name | still noisy for multi-case builds
Confidence: high
Scope-risk: narrow
Tested: Focused naming tests fail against current implementation"
```

## Task 2: Implement Sequence-Based Job Name Generation

**Files:**
- Modify: `app/services/print_queue_service.py`
- Test: `tests/test_integration.py`

- [ ] **Step 1: Update constants and remove unused hash/token helpers**

In `app/services/print_queue_service.py`, remove `import hashlib`, `PRINT_JOB_NAME_HASH_LENGTH`, `_UNSAFE_JOB_NAME_CHARS`, `_safe_job_name_token()`, and `_fit_job_name_to_limit()`.

Keep `import re` and add this constant near `MAX_PRINT_JOB_NAME_LENGTH`:

```python
DAILY_PRINT_JOB_SEQUENCE_LIMIT = 9999
_SEQUENCE_JOB_NAME_RE = re.compile(r"^(?P<date>\d{6})_(?P<sequence>\d{4})$")
```

- [ ] **Step 2: Add a sequence chooser helper**

Add this helper above `generate_job_name()`:

```python
def _next_daily_sequence_job_name(date_part: str, existing_names: set[str] | None) -> str:
    reserved_names = existing_names or set()
    used_sequences: set[int] = set()

    for name in reserved_names:
        match = _SEQUENCE_JOB_NAME_RE.fullmatch(name)
        if match is None or match.group("date") != date_part:
            continue
        used_sequences.add(int(match.group("sequence")))

    for sequence in range(1, DAILY_PRINT_JOB_SEQUENCE_LIMIT + 1):
        candidate = f"{date_part}_{sequence:04d}"
        if sequence not in used_sequences and candidate not in reserved_names:
            return candidate

    raise RuntimeError("Could not generate a unique daily print job name.")
```

- [ ] **Step 3: Replace `generate_job_name()` implementation**

Replace the function body and docstring with:

```python
def generate_job_name(
    date: datetime,
    case_ids: Iterable[str],
    *,
    existing_names: set[str] | None = None,
) -> str:
    """Generate a file-safe YYMMDD_XXXX daily sequence job name.

    case_ids is accepted for call-site compatibility. Case traceability is
    stored separately on PrintJob.case_ids and manifest_json.
    """
    del case_ids
    date_part = date.strftime("%y%m%d")
    return _next_daily_sequence_job_name(date_part, existing_names)
```

- [ ] **Step 4: Run focused naming tests**

Run:

```powershell
pytest tests/test_integration.py::TestFullPrintHandoffFlow::test_job_names_use_daily_sequence tests/test_integration.py::TestFullPrintHandoffFlow::test_job_name_sequence_fails_after_daily_limit -v
```

Expected: both tests pass.

- [ ] **Step 5: Run a syntax/import check for the service**

Run:

```powershell
python -m py_compile app/services/print_queue_service.py
```

Expected: command exits with code `0`.

- [ ] **Step 6: Commit implementation**

Run:

```powershell
git add app/services/print_queue_service.py
git commit -m "Generate print job names from daily sequences" -m "Job names now use the YYMMDD_XXXX operational format while existing call sites keep passing case IDs for metadata and compatibility.

Constraint: Existing call sites pass case_ids into generate_job_name
Rejected: Add a database sequence table | unnecessary because same-day print_jobs already provide the reservation set
Confidence: high
Scope-risk: narrow
Tested: Focused naming tests; py_compile for print_queue_service.py"
```

## Task 3: Update Handoff Expectations While Preserving Cases Display Data

**Files:**
- Modify: `tests/test_preform_handoff.py`
- Test: `tests/test_preform_handoff.py`

- [ ] **Step 1: Update same-day dedupe test**

Rename `test_send_to_print_dedupes_descriptive_job_name_for_today` to:

```python
def test_send_to_print_uses_next_daily_sequence_for_today(tmp_path):
```

In that test, seed an existing sequence job instead of a descriptive job:

```python
    create_print_job(
        settings,
        PrintJob(
            job_name=f"{today_prefix}_0001",
            preset="Ortho Solid - Flat, No Supports",
            status="Queued",
            case_ids=["CASE-NEXT-JOB"],
        ),
    )
```

Replace the final expectations with:

```python
    assert [job.job_name for job in jobs] == [
        f"{today_prefix}_0002",
        f"{today_prefix}_0001",
    ]
    assert jobs[0].case_ids == ["CASE-NEXT-JOB"]
    assert stub_client.print_jobs == [("scene-1", "Form 4BL", f"{today_prefix}_0002")]
```

- [ ] **Step 2: Update mixed compatible preset job name expectation**

In `test_send_to_print_persists_mixed_compatible_presets`, replace:

```python
    assert jobs[0].job_name == f"{datetime.now().strftime('%y%m%d')}_CASE-A_CASE-B"
```

with:

```python
    assert jobs[0].job_name == f"{datetime.now().strftime('%y%m%d')}_0001"
    assert jobs[0].case_ids == ["CASE-A", "CASE-B"]
```

Keep the existing assertion:

```python
    assert jobs[0].manifest_json["case_ids"] == ["CASE-A", "CASE-B"]
```

- [ ] **Step 3: Update validation warning expected form path**

In `test_send_to_print_records_validation_warnings_without_rollback`, replace:

```python
    expected_job_name = f"{datetime.now().strftime('%y%m%d')}_CASE-INVALID"
```

with:

```python
    expected_job_name = f"{datetime.now().strftime('%y%m%d')}_0001"
```

- [ ] **Step 4: Update linked history job name expectation**

In `test_send_to_print_moves_submitted_rows_to_history`, replace:

```python
    assert row["linked_job_name"] == f"{datetime.now().strftime('%y%m%d')}_CASE-HISTORY"
```

with:

```python
    assert row["linked_job_name"] == f"{datetime.now().strftime('%y%m%d')}_0001"
```

- [ ] **Step 5: Update PreForm scene creation expectation**

In `test_send_to_print_does_not_require_volume_before_handoff`, replace:

```python
    assert stub_client.created_scenes == [
        ("CASE-VOLUME", f"{datetime.now().strftime('%y%m%d')}_CASE-VOLUME")
    ]
```

with:

```python
    assert stub_client.created_scenes == [
        ("CASE-VOLUME", f"{datetime.now().strftime('%y%m%d')}_0001")
    ]
```

- [ ] **Step 6: Search for remaining case-ID job name assertions**

Run:

```powershell
rg -n "strftime\('%y%m%d'\).*CASE|today_prefix.*CASE|CASE-.*_02|CASE-A_CASE-B|linked_job_name.*%y%m%d|expected_job_name" tests app
```

Expected: no remaining assertions that require case IDs inside `job_name`. If a result is an assertion for `case_ids`, keep it.

- [ ] **Step 7: Run focused handoff tests**

Run:

```powershell
pytest tests/test_preform_handoff.py::test_send_to_print_uses_next_daily_sequence_for_today tests/test_preform_handoff.py::test_send_to_print_persists_mixed_compatible_presets tests/test_preform_handoff.py::test_send_to_print_records_validation_warnings_without_rollback tests/test_preform_handoff.py::test_send_to_print_moves_submitted_rows_to_history tests/test_preform_handoff.py::test_send_to_print_does_not_require_volume_before_handoff -v
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit handoff test updates**

Run:

```powershell
git add tests/test_preform_handoff.py
git commit -m "Align handoff tests with short print job names" -m "Handoff expectations now treat job_name as a daily sequence while continuing to assert case IDs through job metadata and manifests.

Constraint: Output artifact paths are derived from job_name
Rejected: Remove case assertions from handoff tests | queue traceability depends on case_ids staying intact
Confidence: high
Scope-risk: narrow
Tested: Focused preform handoff tests"
```

## Task 4: Verify Queue Case Display Contract and Regression Surface

**Files:**
- Inspect: `app/static/app.js`
- Test: `tests/test_integration.py`, `tests/test_preform_handoff.py`, `tests/test_print_queue.py`, `tests/test_print_queue_polling.py`

- [ ] **Step 1: Confirm Cases display still reads `job.case_ids`**

Run:

```powershell
rg -n "job\\.case_ids|casesCell|job-cases|Show Cases|Hide Cases" app/static/app.js
```

Expected output includes these existing render paths:

```text
casesCell.textContent = (job.case_ids || []).length > 0 ? job.case_ids.join(", ") : "-";
casesHeader.textContent = isExpanded ? `Hide Cases (${job.case_ids.length})` : `Show Cases (${job.case_ids.length})`;
job.case_ids.forEach((caseId) => {
```

- [ ] **Step 2: Run print queue and handoff regression tests**

Run:

```powershell
pytest tests/test_integration.py tests/test_preform_handoff.py tests/test_print_queue.py tests/test_print_queue_polling.py -v
```

Expected: all selected tests pass.

- [ ] **Step 3: Run frontend static checks if JavaScript changed**

If `git diff -- app/static/app.js` shows no diff, record this as not applicable. If `app/static/app.js` changed, run:

```powershell
pytest tests/test_frontend_static.py -v
```

Expected: all selected tests pass.

- [ ] **Step 4: Check full repository status for the implementation files**

Run:

```powershell
git status --short app/services/print_queue_service.py tests/test_integration.py tests/test_preform_handoff.py app/static/app.js app/schemas.py
```

Expected: only intentional implementation files appear before the final commit. Pre-existing unrelated dirty files outside this path set remain untouched.

- [ ] **Step 5: Commit final verification note if no code changes remain unstaged**

If Task 4 made no code changes, do not create an empty commit. If Task 4 required a small correction, commit only that correction with:

```powershell
git add <corrected-files>
git commit -m "Preserve queue case display with sequence job names" -m "Verification confirmed the print queue still renders cases from job.case_ids after job_name was simplified.

Constraint: Operators still need case visibility in Print Queue
Confidence: high
Scope-risk: narrow
Tested: Print queue and handoff regression tests"
```

## Task 5: Live PreFormServer Completion Proof

**Files:**
- No planned code changes
- Evidence source: live app and PreFormServer endpoints

- [ ] **Step 1: Start or attach to the app**

Run:

```powershell
uvicorn app.main:app --reload --port 8090
```

Expected: app serves `http://127.0.0.1:8090`.

- [ ] **Step 2: Verify app health**

Run in a second shell:

```powershell
curl http://127.0.0.1:8090/health
curl http://127.0.0.1:8090/health/ready
```

Expected: both endpoints return successful health payloads.

- [ ] **Step 3: Verify live PreFormServer readiness**

Run:

```powershell
curl http://127.0.0.1:8090/api/preform-setup/status
```

Expected: JSON includes `"readiness":"ready"`.

- [ ] **Step 4: Run a task-specific handoff proof**

Use the existing browser/UI or API happy path to send at least one ready STL row to print handoff. Confirm the resulting print queue job has:

```text
job_name: YYMMDD_0001 or the next same-day sequence
case_ids: the submitted case ID list
form_file_path: output/<job_name>/<job_name>.form
```

- [ ] **Step 5: Record blocker if live proof cannot run**

If PreFormServer cannot be started or readiness is not `"ready"`, do not claim completion. Final reporting must state:

```text
Live PreFormServer completion proof is blocked because /api/preform-setup/status did not report readiness=ready.
```

## Self-Review

- Spec coverage:
  - Daily `YYMMDD_XXXX` naming: Task 1 and Task 2.
  - Existing historical jobs not renamed: Task 2 uses only new generation and does not migrate data.
  - Cases display preserved: Task 3 keeps `case_ids` assertions; Task 4 inspects UI render paths.
  - Output artifact paths use short name: Task 3 updates expected paths through `expected_job_name` and existing `jobs[0].job_name` path checks.
  - No new database sequence table: Task 2 derives sequences from existing same-day `print_jobs`.
  - Exhaustion error: Task 1 and Task 2 cover the runtime error.
- Placeholder scan:
  - No placeholder markers or undefined future steps remain.
- Type consistency:
  - `generate_job_name(date: datetime, case_ids: Iterable[str], existing_names: set[str] | None = None) -> str` remains compatible with current call sites.
  - `PrintJob.case_ids`, `manifest_json`, and `job.job_name` names match existing schema and service usage.
