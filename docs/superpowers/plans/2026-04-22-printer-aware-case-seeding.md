# Printer-Aware Case Seeding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update `Andent_Webapp` build planning so `Form 4B` starts new builds by attempting the largest 3 cases, `Form 4BL` starts by attempting the largest 8 cases, then continues descending until the first fit failure and finally switches to smallest fillers.

**Architecture:** Keep all selection logic inside `app/services/build_planning.py`. Reuse existing `CasePackProfile`, `_profile_priority(...)`, compatibility grouping, and XY-budget fit checks. Do not duplicate selection logic in runtime handoff code.

**Tech Stack:** Python, Pydantic models in `app/schemas.py`, pytest, existing preset catalog and XY-budget heuristic

---

## File Structure

**Primary files**
- Modify: `app/services/build_planning.py`
  Responsibility: planner-owned case ordering, startup seeding, descending pass, filler pass, manifest construction
- Modify: `tests/test_build_planning.py`
  Responsibility: lock the intended planner behavior with TDD-first regression tests

**Read-only references**
- Read: `app/services/preset_catalog.py`
  Responsibility: printer metadata and XY budget lookup already used by the planner
- Read: `app/schemas.py`
  Responsibility: `CasePackProfile`, `BuildManifest`, and `FilePrepSpec` shapes the planner already returns

**No changes required**
- `app/services/print_queue_service.py`
- routers, schemas, database, or `FormFlow_Dent`

---

### Task 1: Lock Printer-Aware Startup Seeding With Failing Tests

**Files:**
- Modify: `tests/test_build_planning.py`
- Read: `app/services/build_planning.py`
- Read: `app/services/preset_catalog.py`

- [ ] **Step 1: Write the failing Form 4B startup-window test**

Add this test near the other planner-ordering tests in `tests/test_build_planning.py`:

```python
def test_plan_build_manifests_form4b_attempts_three_largest_cases_before_fillers(monkeypatch):
    monkeypatch.setitem(
        PRESET_CATALOG,
        "Form 4B Experimental",
        PresetProfile(
            preset_name="Form 4B Experimental",
            printer="Form 4B",
            resin="Precision Model Resin",
            layer_height_microns=100,
            requires_supports=False,
            preform_hint="form4b_experimental_v1",
        ),
    )

    rows = [
        _row(1, "CASE-A", "Form 4B Experimental", 90.0, 60.0),
        _row(2, "CASE-B", "Form 4B Experimental", 85.0, 60.0),
        _row(3, "CASE-C", "Form 4B Experimental", 80.0, 60.0),
        _row(4, "CASE-D", "Form 4B Experimental", 35.0, 20.0),
    ]

    manifests = plan_build_manifests(rows)

    assert manifests[0].case_ids == ["CASE-A", "CASE-B", "CASE-D"]
    assert manifests[1].case_ids == ["CASE-C"]
```

- [ ] **Step 2: Run the Form 4B test to verify it fails**

Run:

```bash
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest tests/test_build_planning.py -k "form4b_attempts_three_largest_cases_before_fillers" -q
```

Expected: FAIL because the current planner still greedily descends and does not treat the first 3 cases as a startup window with an early switch to fillers after the first descending miss.

- [ ] **Step 3: Write the failing Form 4BL startup-window test**

Add this second test in `tests/test_build_planning.py`:

```python
def test_plan_build_manifests_form4bl_attempts_eight_largest_cases_before_fillers(monkeypatch):
    monkeypatch.setitem(
        PRESET_CATALOG,
        "Form 4BL Experimental",
        PresetProfile(
            preset_name="Form 4BL Experimental",
            printer="Form 4BL",
            resin="Precision Model Resin",
            layer_height_microns=100,
            requires_supports=False,
            preform_hint="form4bl_experimental_v1",
        ),
    )

    rows = [
        _row(1, "CASE-01", "Form 4BL Experimental", 90.0, 45.0),
        _row(2, "CASE-02", "Form 4BL Experimental", 88.0, 45.0),
        _row(3, "CASE-03", "Form 4BL Experimental", 86.0, 45.0),
        _row(4, "CASE-04", "Form 4BL Experimental", 84.0, 45.0),
        _row(5, "CASE-05", "Form 4BL Experimental", 82.0, 45.0),
        _row(6, "CASE-06", "Form 4BL Experimental", 80.0, 45.0),
        _row(7, "CASE-07", "Form 4BL Experimental", 78.0, 45.0),
        _row(8, "CASE-08", "Form 4BL Experimental", 76.0, 45.0),
        _row(9, "CASE-09", "Form 4BL Experimental", 74.0, 45.0),
        _row(10, "CASE-10", "Form 4BL Experimental", 20.0, 20.0),
    ]

    manifests = plan_build_manifests(rows)

    assert manifests[0].case_ids == [
        "CASE-01",
        "CASE-02",
        "CASE-03",
        "CASE-04",
        "CASE-05",
        "CASE-06",
        "CASE-07",
        "CASE-08",
        "CASE-10",
    ]
    assert manifests[1].case_ids == ["CASE-09"]
```

- [ ] **Step 4: Run the Form 4BL test to verify it fails**

Run:

```bash
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest tests/test_build_planning.py -k "form4bl_attempts_eight_largest_cases_before_fillers" -q
```

Expected: FAIL because the current planner does not explicitly enforce the 8-case startup phase before switching to the filler phase.

- [ ] **Step 5: Add the threshold fallback test before implementation**

Add this third test:

```python
def test_plan_build_manifests_form4bl_below_threshold_keeps_seed_with_largest_behavior(monkeypatch):
    monkeypatch.setitem(
        PRESET_CATALOG,
        "Form 4BL Experimental",
        PresetProfile(
            preset_name="Form 4BL Experimental",
            printer="Form 4BL",
            resin="Precision Model Resin",
            layer_height_microns=100,
            requires_supports=False,
            preform_hint="form4bl_experimental_v1",
        ),
    )

    rows = [
        _row(1, "CASE-A", "Form 4BL Experimental", 120.0, 60.0),
        _row(2, "CASE-B", "Form 4BL Experimental", 70.0, 40.0),
        _row(3, "CASE-C", "Form 4BL Experimental", 60.0, 35.0),
    ]

    manifests = plan_build_manifests(rows)

    assert manifests[0].case_ids == ["CASE-A", "CASE-B", "CASE-C"]
```

- [ ] **Step 6: Run the three new tests together and verify at least the first two fail**

Run:

```bash
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest tests/test_build_planning.py -k "form4b_attempts_three_largest_cases_before_fillers or form4bl_attempts_eight_largest_cases_before_fillers or form4bl_below_threshold_keeps_seed_with_largest_behavior" -q
```

Expected: at least the first two tests FAIL under current behavior; the fallback test may already pass.

- [ ] **Step 7: Commit the failing-test baseline**

```bash
git add tests/test_build_planning.py
git commit -m "Lock printer-aware startup seeding expectations before planner changes

Capture the intended Form 4B and Form 4BL startup-window behavior in tests
before changing the planner loop. This keeps the behavior change explicit and
prevents silent drift in case ordering rules.

Constraint: Fit checks must remain XY-budget heuristic only for this change
Rejected: Add live scene-fit probe coverage now | unnecessary scope and test cost
Confidence: high
Scope-risk: narrow
Directive: Keep runtime handoff out of this feature; ordering is planner-owned
Tested: Targeted build-planning red tests
Not-tested: Full planner suite after implementation"
```

---

### Task 2: Implement Printer-Aware Startup, Descending, and Filler Phases

**Files:**
- Modify: `app/services/build_planning.py`
- Read: `app/services/preset_catalog.py`
- Test: `tests/test_build_planning.py`

- [ ] **Step 1: Add a failing helper-selection test if helper extraction needs a direct unit**

Only if you decide the helper should be directly tested, add:

```python
def test_plan_build_manifests_respects_printer_specific_startup_window(monkeypatch):
    monkeypatch.setitem(
        PRESET_CATALOG,
        "Form 4B Experimental",
        PresetProfile(
            preset_name="Form 4B Experimental",
            printer="Form 4B",
            resin="Precision Model Resin",
            layer_height_microns=100,
            requires_supports=False,
            preform_hint="form4b_experimental_v1",
        ),
    )

    rows = [
        _row(1, "CASE-A", "Form 4B Experimental", 10.0, 10.0),
        _row(2, "CASE-B", "Form 4B Experimental", 9.0, 10.0),
        _row(3, "CASE-C", "Form 4B Experimental", 8.0, 10.0),
        _row(4, "CASE-D", "Form 4B Experimental", 7.0, 10.0),
    ]

    manifests = plan_build_manifests(rows)

    assert manifests[0].case_ids[:3] == ["CASE-A", "CASE-B", "CASE-C"]
```

- [ ] **Step 2: Add a printer-aware startup-count helper in `app/services/build_planning.py`**

Insert a helper near `_profile_xy_budget(...)`:

```python
def _startup_case_count(profile: CasePackProfile) -> int:
    if not profile.file_specs:
        return 1
    profile_details = get_preset_profile(profile.file_specs[0].preset_name)
    printer_name = profile_details.printer if profile_details is not None else None
    if printer_name == "Form 4B":
        return 3
    if printer_name == "Form 4BL":
        return 8
    return 1
```

- [ ] **Step 3: Add a focused fit helper so the loop logic is readable**

In the same file add:

```python
def _fits_with_profile(
    used_xy: float,
    candidate: CasePackProfile,
    xy_budget: float,
) -> bool:
    return used_xy + candidate.total_xy_footprint <= xy_budget
```

- [ ] **Step 4: Replace the current seed-plus-greedy loop with explicit phases**

Update the loop inside `plan_build_manifests(...)` so it follows this structure:

```python
        seed = remaining.pop(0)
        chosen = [seed]
        used = seed.total_xy_footprint
        xy_budget = _profile_xy_budget(seed)
        startup_count = _startup_case_count(seed)

        if len(remaining) + 1 >= startup_count:
            startup_candidates = list(remaining[: startup_count - 1])
            for candidate in startup_candidates:
                if candidate in remaining and _fits_with_profile(used, candidate, xy_budget):
                    chosen.append(candidate)
                    used += candidate.total_xy_footprint
                    remaining.remove(candidate)

        descending_failed = False
        for candidate in list(remaining):
            if _fits_with_profile(used, candidate, xy_budget):
                chosen.append(candidate)
                used += candidate.total_xy_footprint
                remaining.remove(candidate)
                continue
            descending_failed = True
            break

        if descending_failed:
            fillers = sorted(
                remaining,
                key=lambda profile: (profile.total_xy_footprint, profile.case_id),
            )
            for filler in list(fillers):
                if filler in remaining and _fits_with_profile(used, filler, xy_budget):
                    chosen.append(filler)
                    used += filler.total_xy_footprint
                    remaining.remove(filler)
```

- [ ] **Step 5: Run the targeted startup-window tests and verify they pass**

Run:

```bash
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest tests/test_build_planning.py -k "form4b_attempts_three_largest_cases_before_fillers or form4bl_attempts_eight_largest_cases_before_fillers or form4bl_below_threshold_keeps_seed_with_largest_behavior" -q
```

Expected: PASS

- [ ] **Step 6: Run the existing ordering and filler regressions**

Run:

```bash
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest tests/test_build_planning.py -k "uses_smallest_case_fillers_after_large_cases_do_not_fit or prefers_next_largest_fit_before_small_fillers or preserves_case_cohesion or allows_mixed_compatible_presets_to_share_one_build" -q
```

Expected: PASS

- [ ] **Step 7: Commit the planner implementation**

```bash
git add app/services/build_planning.py tests/test_build_planning.py
git commit -m "Align build composition with printer-aware startup case seeding

Make the planner explicitly follow a three-phase selection policy: startup
window, descending pass, then smallest fillers. The startup window now depends
on printer family so Form 4B and Form 4BL front-load different numbers of
largest remaining cases.

Constraint: Selection logic must stay planner-owned and keep the XY-budget heuristic
Rejected: Duplicate ordering rules in runtime handoff | would create planner/runtime drift
Confidence: high
Scope-risk: narrow
Directive: Keep whole-case cohesion and compatibility grouping intact when changing order
Tested: Targeted build-planning tests
Not-tested: Full repository suite"
```

---

### Task 3: Add Transition and Regression Coverage, Then Verify the Full Planner File

**Files:**
- Modify: `tests/test_build_planning.py`
- Modify: `app/services/build_planning.py` if cleanup is needed

- [ ] **Step 1: Add a direct regression for “stop descending on first miss, then use fillers”**

Add this test to `tests/test_build_planning.py`:

```python
def test_plan_build_manifests_switches_to_fillers_after_first_descending_fit_failure(monkeypatch):
    monkeypatch.setitem(
        PRESET_CATALOG,
        "Form 4BL Experimental",
        PresetProfile(
            preset_name="Form 4BL Experimental",
            printer="Form 4BL",
            resin="Precision Model Resin",
            layer_height_microns=100,
            requires_supports=False,
            preform_hint="form4bl_experimental_v1",
        ),
    )

    rows = [
        _row(1, "CASE-A", "Form 4BL Experimental", 200.0, 100.0),
        _row(2, "CASE-B", "Form 4BL Experimental", 75.0, 60.0),
        _row(3, "CASE-C", "Form 4BL Experimental", 74.0, 60.0),
        _row(4, "CASE-D", "Form 4BL Experimental", 73.0, 60.0),
        _row(5, "CASE-E", "Form 4BL Experimental", 72.0, 60.0),
        _row(6, "CASE-F", "Form 4BL Experimental", 71.0, 60.0),
        _row(7, "CASE-G", "Form 4BL Experimental", 70.0, 60.0),
        _row(8, "CASE-H", "Form 4BL Experimental", 69.0, 60.0),
        _row(9, "CASE-I", "Form 4BL Experimental", 68.0, 60.0),
        _row(10, "CASE-SMALL", "Form 4BL Experimental", 20.0, 20.0),
    ]

    manifests = plan_build_manifests(rows)

    assert "CASE-SMALL" in manifests[0].case_ids
    assert "CASE-I" not in manifests[0].case_ids
```

- [ ] **Step 2: Run the new transition test to verify it passes**

Run:

```bash
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest tests/test_build_planning.py -k "switches_to_fillers_after_first_descending_fit_failure" -q
```

Expected: PASS

- [ ] **Step 3: Run the full build-planning test file**

Run:

```bash
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest tests/test_build_planning.py -q
```

Expected: PASS for the full file.

- [ ] **Step 4: Run the dependent integration tests that exercise manifest creation**

Run:

```bash
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest tests/test_batching.py tests/test_integration.py -q
```

Expected: PASS

- [ ] **Step 5: If any old tests fail due to previous implicit ordering assumptions, update only those assertions that conflict with the approved strategy**

Use this rule when adjusting assertions:

```python
assert manifest.case_ids == expected_case_order_under_new_strategy
```

Do not weaken assertions to unordered sets unless the feature genuinely does not require order.

- [ ] **Step 6: Commit the regression coverage and final verification state**

```bash
git add tests/test_build_planning.py app/services/build_planning.py
git commit -m "Harden planner regressions for startup seeding and filler transition

Add explicit regression coverage for the new startup-window and descending-to-filler
transition behavior so the intended build composition strategy remains locked.

Constraint: Existing test coverage must stay order-sensitive where planner order matters
Rejected: Convert order assertions to sets | would hide strategy regressions
Confidence: high
Scope-risk: narrow
Directive: Future planner changes must keep printer-aware startup seeding explicit in tests
Tested: build_planning, batching, integration pytest runs
Not-tested: Live PreFormServer handoff against this new planner ordering"
```

---

## Self-Review

### Spec coverage

Spec requirement to task mapping:

1. Printer-aware startup windows in planner only -> Task 2
2. `Form 4B` threshold `3` -> Task 1 and Task 2
3. `Form 4BL` threshold `8` -> Task 1 and Task 2
4. Descending pass then smallest fillers -> Task 2 and Task 3
5. Keep XY-budget heuristic fit signal -> Task 2
6. Preserve case cohesion and compatibility grouping -> Task 2 verification and Task 3 regression runs

No spec gaps remain.

### Placeholder scan

Checked for:
- `TODO`
- `TBD`
- vague “add validation” wording
- undefined helper names

No placeholders remain.

### Type consistency

The plan uses the existing repo types and names consistently:
- `CasePackProfile`
- `BuildManifest`
- `_profile_priority(...)`
- `get_preset_profile(...)`
- `plan_build_manifests(...)`

No naming drift found.
