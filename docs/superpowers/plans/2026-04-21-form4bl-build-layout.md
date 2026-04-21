# Form 4BL Build Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace preset-only print batching with compatibility-aware, whole-case Form 4BL build planning that preserves per-file preset application and never splits a case across builds.

**Architecture:** Add a preset catalog as the single source of truth for derived printer/material settings, then add a dedicated build-planning service that computes case-level XY envelopes and emits build manifests. Refactor the print handoff service to consume those manifests, import files grouped by preset hint, run PreFormServer auto-layout plus validation, and roll back whole cases when a candidate build fails validation.

**Tech Stack:** FastAPI, Pydantic, SQLite, pytest, vanilla JS, existing PreFormServer HTTP client

---

## File Structure

### New Files

- `app/services/preset_catalog.py`
  Owns preset metadata, compatibility rules, preset summaries, and the mapping from UI preset name to PreFormServer hint.
- `app/services/build_planning.py`
  Owns file-level prep specs, case pack profiles, build candidates, build manifests, and the largest-first then smallest-filler heuristic.
- `tests/test_preset_catalog.py`
  Verifies preset-derived printer/resin/layer/support compatibility behavior.
- `tests/test_build_planning.py`
  Verifies whole-case grouping, XY footprint estimation, sort order, filler behavior, and no-case-splitting.

### Existing Files To Modify

- `app/services/classification.py`
  Switch default preset handling to use the preset catalog instead of hardcoded mapping.
- `app/services/preform_client.py`
  Add `auto_layout()` and `validate_scene()` support needed by the new handoff loop.
- `app/services/print_queue_service.py`
  Replace `batch_cases_by_preset()` usage with compatibility-aware build planning and grouped import by manifest.
- `app/services/planning_preview.py`
  Update preview grouping to use compatibility-aware build planning instead of preset-only grouping.
- `app/schemas.py`
  Add planning and manifest schema models plus print queue fields for mixed-preset builds.
- `app/database.py`
  Persist new print job metadata such as compatible preset lists and manifest JSON.
- `app/static/app.js`
  Render mixed-preset job summaries in the print queue.
- `tests/test_preset_configuration.py`
  Keep default preset behavior green after moving preset logic behind the catalog.
- `tests/test_preform_client.py`
  Add coverage for `auto_layout()` and `validate_scene()`.
- `tests/test_preform_handoff.py`
  Update send-to-print boundary tests to assert compatibility-aware manifests, grouped imports, and rollback behavior.
- `tests/test_batching.py`
  Replace preset-only batching tests with compatibility-aware build-planning assertions.
- `tests/test_print_queue.py`
  Update print job schema and DB round-trip tests for mixed-preset builds.
- `tests/test_planning_preview.py`
  Update preview expectations to reflect compatibility-aware build grouping.
- `Andent/02_planning/02.02_Architecture-PreFormServer-handoff.md`
  Update the architecture doc after code lands so repo docs match the implemented behavior.

## Task 1: Add The Preset Catalog

**Files:**
- Create: `app/services/preset_catalog.py`
- Modify: `app/services/classification.py`
- Test: `tests/test_preset_catalog.py`
- Test: `tests/test_preset_configuration.py`

- [ ] **Step 1: Write the failing preset-catalog tests**

```python
"""Preset catalog tests for compatibility-aware build planning."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.preset_catalog import (
    build_compatibility_key,
    get_preform_preset_hint,
    get_preset_profile,
    presets_are_compatible,
)


def test_get_preset_profile_derives_form4bl_precision_defaults():
    profile = get_preset_profile("Tooth - With Supports")

    assert profile.preset_name == "Tooth - With Supports"
    assert profile.printer == "Form 4BL"
    assert profile.resin == "Precision Model Resin"
    assert profile.layer_height_microns == 100
    assert profile.requires_supports is True


def test_presets_are_compatible_when_printer_resin_and_layer_match():
    assert presets_are_compatible(
        ["Ortho Solid - Flat, No Supports", "Tooth - With Supports"]
    ) is True


def test_build_compatibility_key_is_stable_for_mixed_compatible_presets():
    key = build_compatibility_key(
        ["Tooth - With Supports", "Ortho Hollow - Flat, No Supports"]
    )

    assert key == "form-4bl|precision-model-resin|100"


def test_get_preform_preset_hint_maps_ui_preset_to_preform_hint():
    assert get_preform_preset_hint("Die - Flat, No Supports") == "die_v1"
```

Run: `pytest tests/test_preset_catalog.py tests/test_preset_configuration.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.preset_catalog'`

- [ ] **Step 2: Implement the preset catalog**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PresetProfile:
    preset_name: str
    printer: str
    resin: str
    layer_height_microns: int
    requires_supports: bool
    preform_hint: str | None


PRESET_CATALOG: dict[str, PresetProfile] = {
    "Ortho Solid - Flat, No Supports": PresetProfile(
        preset_name="Ortho Solid - Flat, No Supports",
        printer="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="ortho_solid_v1",
    ),
    "Ortho Hollow - Flat, No Supports": PresetProfile(
        preset_name="Ortho Hollow - Flat, No Supports",
        printer="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="ortho_hollow_v1",
    ),
    "Die - Flat, No Supports": PresetProfile(
        preset_name="Die - Flat, No Supports",
        printer="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="die_v1",
    ),
    "Tooth - With Supports": PresetProfile(
        preset_name="Tooth - With Supports",
        printer="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
        requires_supports=True,
        preform_hint="tooth_v1",
    ),
    "Splint - Flat, No Supports": PresetProfile(
        preset_name="Splint - Flat, No Supports",
        printer="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="splint_v1",
    ),
    "Antagonist Solid - Flat, No Supports": PresetProfile(
        preset_name="Antagonist Solid - Flat, No Supports",
        printer="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="antagonist_solid_v1",
    ),
    "Antagonist Hollow - Flat, No Supports": PresetProfile(
        preset_name="Antagonist Hollow - Flat, No Supports",
        printer="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="antagonist_hollow_v1",
    ),
}


def get_preset_profile(preset_name: str | None) -> PresetProfile | None:
    if preset_name is None:
        return None
    return PRESET_CATALOG.get(preset_name)


def get_preform_preset_hint(preset_name: str | None) -> str | None:
    profile = get_preset_profile(preset_name)
    return profile.preform_hint if profile else None


def build_compatibility_key(preset_names: list[str]) -> str:
    profiles = [get_preset_profile(name) for name in preset_names]
    if not profiles or any(profile is None for profile in profiles):
        raise ValueError("Cannot build compatibility key for unknown preset.")
    first = profiles[0]
    assert first is not None
    return f"{first.printer.lower()}|{first.resin.lower().replace(' ', '-')}|{first.layer_height_microns}"


def presets_are_compatible(preset_names: list[str]) -> bool:
    profiles = [get_preset_profile(name) for name in preset_names]
    if not profiles or any(profile is None for profile in profiles):
        return False
    printer_resin_layer = {
        (profile.printer, profile.resin, profile.layer_height_microns)
        for profile in profiles
        if profile is not None
    }
    return len(printer_resin_layer) == 1
```

- [ ] **Step 3: Route classification and handoff code through the catalog**

```python
from .preset_catalog import get_preset_profile


def default_preset(model_type: str | None) -> str | None:
    if model_type is None:
        return None
    preset_mappings = {
        "Ortho - Solid": "Ortho Solid - Flat, No Supports",
        "Ortho - Hollow": "Ortho Hollow - Flat, No Supports",
        "Die": "Die - Flat, No Supports",
        "Tooth": "Tooth - With Supports",
        "Splint": "Splint - Flat, No Supports",
        "Antagonist - Solid": "Antagonist Solid - Flat, No Supports",
        "Antagonist - Hollow": "Antagonist Hollow - Flat, No Supports",
    }
    preset = preset_mappings.get(model_type)
    if preset is None:
        return None
    return get_preset_profile(preset).preset_name
```

- [ ] **Step 4: Run the preset tests**

Run: `pytest tests/test_preset_catalog.py tests/test_preset_configuration.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/preset_catalog.py app/services/classification.py tests/test_preset_catalog.py tests/test_preset_configuration.py
git commit -m "feat: centralize preset compatibility metadata"
```

## Task 2: Extend PreFormClient With Layout And Validation

**Files:**
- Modify: `app/services/preform_client.py`
- Test: `tests/test_preform_client.py`

- [ ] **Step 1: Write the failing PreFormClient tests**

```python
def test_auto_layout_posts_scene_id_payload():
    from app.services.preform_client import PreFormClient
    from unittest.mock import Mock, patch

    with patch("requests.Session.post") as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_response

        client = PreFormClient("http://localhost:44388")
        result = client.auto_layout("scene-123")

        assert result == {"status": "ok"}
        mock_post.assert_called_with(
            "http://localhost:44388/scene/scene-123/auto-layout/",
            json={"allow_overlapping_supports": False},
            timeout=30,
        )


def test_validate_scene_returns_clean_boolean_and_errors():
    from app.services.preform_client import PreFormClient
    from unittest.mock import Mock, patch

    with patch("requests.Session.get") as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"valid": False, "errors": ["overlap"]}
        mock_get.return_value = mock_response

        client = PreFormClient("http://localhost:44388")
        result = client.validate_scene("scene-123")

        assert result == {"valid": False, "errors": ["overlap"]}
```

Run: `pytest tests/test_preform_client.py -q`
Expected: FAIL with `AttributeError: 'PreFormClient' object has no attribute 'auto_layout'`

- [ ] **Step 2: Add the new PreFormClient methods**

```python
@retry_on_failure(max_retries=3, backoff_factor=2.0)
def auto_layout(
    self,
    scene_id: str,
    *,
    allow_overlapping_supports: bool = False,
) -> Dict[str, Any]:
    url = f"{self.base_url}/scene/{scene_id}/auto-layout/"
    payload = {"allow_overlapping_supports": allow_overlapping_supports}
    response = self.session.post(url, json=payload, timeout=30)
    if response.status_code != 200:
        raise Exception(f"Failed to auto-layout scene: {response.status_code} - {response.text}")
    return response.json()


@retry_on_failure(max_retries=3, backoff_factor=2.0)
def validate_scene(self, scene_id: str) -> Dict[str, Any]:
    url = f"{self.base_url}/scene/{scene_id}/validate/"
    response = self.session.get(url, timeout=30)
    if response.status_code != 200:
        raise Exception(f"Failed to validate scene: {response.status_code} - {response.text}")
    return response.json()
```

- [ ] **Step 3: Run the PreFormClient tests**

Run: `pytest tests/test_preform_client.py -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add app/services/preform_client.py tests/test_preform_client.py
git commit -m "feat: add preform layout and validation client calls"
```

## Task 3: Add Compatibility-Aware Build Planning

**Files:**
- Create: `app/services/build_planning.py`
- Modify: `app/schemas.py`
- Test: `tests/test_build_planning.py`
- Test: `tests/test_batching.py`

- [ ] **Step 1: Write the failing build-planning tests**

```python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.schemas import ClassificationRow, DimensionSummary
from app.services.build_planning import plan_build_manifests


def _row(row_id: int, case_id: str, preset: str, x: float, y: float) -> ClassificationRow:
    return ClassificationRow(
        row_id=row_id,
        file_name=f"{case_id}-{row_id}.stl",
        case_id=case_id,
        preset=preset,
        confidence="high",
        status="Ready",
        dimensions=DimensionSummary(x_mm=x, y_mm=y, z_mm=10.0),
    )


def test_plan_build_manifests_keeps_case_intact():
    rows = [
        _row(1, "CASE-1", "Ortho Solid - Flat, No Supports", 80.0, 70.0),
        _row(2, "CASE-1", "Tooth - With Supports", 40.0, 30.0),
        _row(3, "CASE-2", "Die - Flat, No Supports", 70.0, 60.0),
    ]

    manifests = plan_build_manifests(rows)

    case_sets = [set(manifest.case_ids) for manifest in manifests]
    assert {"CASE-1"} in case_sets or {"CASE-1", "CASE-2"} in case_sets
    assert sum("CASE-1" in case_ids for case_ids in case_sets) == 1


def test_plan_build_manifests_allows_mixed_compatible_presets():
    rows = [
        _row(1, "CASE-1", "Ortho Solid - Flat, No Supports", 60.0, 50.0),
        _row(2, "CASE-2", "Tooth - With Supports", 35.0, 35.0),
    ]

    manifests = plan_build_manifests(rows)

    assert len(manifests) == 1
    assert manifests[0].preset_names == [
        "Ortho Solid - Flat, No Supports",
        "Tooth - With Supports",
    ]


def test_plan_build_manifests_uses_smallest_cases_as_fillers():
    rows = [
        _row(1, "CASE-L", "Ortho Solid - Flat, No Supports", 100.0, 90.0),
        _row(2, "CASE-M", "Ortho Solid - Flat, No Supports", 80.0, 70.0),
        _row(3, "CASE-S1", "Die - Flat, No Supports", 30.0, 20.0),
        _row(4, "CASE-S2", "Die - Flat, No Supports", 28.0, 18.0),
    ]

    manifests = plan_build_manifests(rows)

    assert manifests[0].case_ids[0] == "CASE-L"
    assert "CASE-S2" in manifests[0].case_ids
```

Run: `pytest tests/test_build_planning.py tests/test_batching.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.build_planning'`

- [ ] **Step 2: Add the planning schema models**

```python
class FilePrepSpec(BaseModel):
    row_id: int
    case_id: str
    file_name: str
    file_path: str
    preset_name: str
    compatibility_key: str
    xy_footprint_estimate: float
    support_inflation_factor: float


class BuildManifestImportGroup(BaseModel):
    preset_name: str
    preform_hint: str | None = None
    row_ids: list[int] = Field(default_factory=list)


class CasePackProfile(BaseModel):
    case_id: str
    compatibility_key: str
    preset_groups: dict[str, list[int]] = Field(default_factory=dict)
    total_xy_footprint: float
    difficulty_score: float
    file_count: int


class BuildCandidate(BaseModel):
    compatibility_key: str
    case_ids: list[str] = Field(default_factory=list)
    used_xy_budget: float = 0.0
    remaining_xy_budget: float = 0.0


class BuildManifest(BaseModel):
    compatibility_key: str
    case_ids: list[str] = Field(default_factory=list)
    preset_names: list[str] = Field(default_factory=list)
    import_groups: list[BuildManifestImportGroup] = Field(default_factory=list)
```

- [ ] **Step 3: Implement the build planner**

```python
FORM4BL_XY_BUDGET = 29000.0
SUPPORT_INFLATION = 1.18


def _row_xy_area(row: ClassificationRow) -> float:
    if row.dimensions is None:
        return 0.0
    return float(row.dimensions.x_mm * row.dimensions.y_mm)


def _support_factor(preset_name: str) -> float:
    profile = get_preset_profile(preset_name)
    if profile is None:
        return 1.0
    return SUPPORT_INFLATION if profile.requires_supports else 1.0


def _case_profile(case_id: str, rows: list[ClassificationRow]) -> CasePackProfile:
    preset_names = sorted({row.preset for row in rows if row.preset})
    compatibility_key = build_compatibility_key(preset_names)
    total_xy = sum(_row_xy_area(row) * _support_factor(row.preset or "") for row in rows)
    difficulty = max(_row_xy_area(row) for row in rows) + total_xy
    preset_groups: dict[str, list[int]] = {}
    for row in rows:
        assert row.row_id is not None
        preset_groups.setdefault(row.preset, []).append(row.row_id)
    return CasePackProfile(
        case_id=case_id,
        compatibility_key=compatibility_key,
        preset_groups=preset_groups,
        total_xy_footprint=total_xy,
        difficulty_score=difficulty,
        file_count=len(rows),
    )


def _group_case_profiles(rows: list[ClassificationRow]) -> list[CasePackProfile]:
    rows_by_case: dict[str, list[ClassificationRow]] = {}
    for row in rows:
        rows_by_case.setdefault(row.case_id or "", []).append(row)
    return [_case_profile(case_id, case_rows) for case_id, case_rows in rows_by_case.items() if case_id]


def _group_profiles_by_compatibility(
    profiles: list[CasePackProfile],
) -> dict[str, list[CasePackProfile]]:
    grouped: dict[str, list[CasePackProfile]] = {}
    for profile in profiles:
        grouped.setdefault(profile.compatibility_key, []).append(profile)
    return grouped


def _build_manifest(compatibility_key: str, profiles: list[CasePackProfile]) -> BuildManifest:
    import_groups: dict[str, list[int]] = {}
    preset_names: list[str] = []
    for profile in profiles:
        for preset_name, row_ids in profile.preset_groups.items():
            preset_names.append(preset_name)
            import_groups.setdefault(preset_name, []).extend(row_ids)
    return BuildManifest(
        compatibility_key=compatibility_key,
        case_ids=[profile.case_id for profile in profiles],
        preset_names=sorted(set(preset_names)),
        import_groups=[
            BuildManifestImportGroup(
                preset_name=preset_name,
                preform_hint=get_preform_preset_hint(preset_name),
                row_ids=row_ids,
            )
            for preset_name, row_ids in sorted(import_groups.items())
        ],
    )


def plan_build_manifests(rows: list[ClassificationRow]) -> list[BuildManifest]:
    ready_rows = [row for row in rows if row.status == "Ready" and row.preset and row.case_id]
    cases = _group_case_profiles(ready_rows)
    manifests: list[BuildManifest] = []
    for compatibility_key, profiles in _group_profiles_by_compatibility(cases).items():
        remaining = sorted(profiles, key=lambda p: (-p.difficulty_score, -p.total_xy_footprint, p.case_id))
        while remaining:
            seed = remaining.pop(0)
            chosen = [seed]
            used = seed.total_xy_footprint
            index = 0
            while index < len(remaining):
                candidate = remaining[index]
                if used + candidate.total_xy_footprint <= FORM4BL_XY_BUDGET:
                    chosen.append(candidate)
                    used += candidate.total_xy_footprint
                    remaining.pop(index)
                    continue
                index += 1
            fillers = sorted(remaining, key=lambda p: (p.total_xy_footprint, p.case_id))
            for filler in list(fillers):
                if used + filler.total_xy_footprint <= FORM4BL_XY_BUDGET and filler in remaining:
                    chosen.append(filler)
                    used += filler.total_xy_footprint
                    remaining.remove(filler)
            manifests.append(_build_manifest(compatibility_key, chosen))
    return manifests
```

- [ ] **Step 4: Run the planning tests**

Run: `pytest tests/test_build_planning.py tests/test_batching.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/build_planning.py app/schemas.py tests/test_build_planning.py tests/test_batching.py
git commit -m "feat: add compatibility-aware form 4bl build planning"
```

## Task 4: Persist Mixed-Preset Build Metadata

**Files:**
- Modify: `app/database.py`
- Modify: `app/schemas.py`
- Test: `tests/test_print_queue.py`

- [ ] **Step 1: Write the failing print-job persistence tests**

```python
def test_print_job_schema_supports_mixed_preset_names():
    from app.schemas import PrintJob

    job = PrintJob(
        job_name="260421-001",
        preset="Mixed Compatible Presets",
        preset_names=["Ortho Solid - Flat, No Supports", "Tooth - With Supports"],
    )

    assert job.preset_names == [
        "Ortho Solid - Flat, No Supports",
        "Tooth - With Supports",
    ]


def test_print_jobs_table_has_preset_names_and_manifest_json(tmp_path):
    from app.database import connect, init_db

    settings = _test_settings(tmp_path)
    init_db(settings)

    with connect(settings) as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(print_jobs)").fetchall()
        }

    assert {"preset_names_json", "manifest_json", "compatibility_key"}.issubset(columns)
```

Run: `pytest tests/test_print_queue.py -q`
Expected: FAIL because `preset_names` and new DB columns do not exist yet

- [ ] **Step 2: Add the new schema and database fields**

```python
class PrintJob(BaseModel):
    id: int | None = None
    job_name: str = Field(pattern=r"^\d{6}-\d{3}$")
    scene_id: str | None = None
    print_job_id: str | None = None
    status: PrintJobStatus = "Queued"
    preset: str
    preset_names: list[str] = Field(default_factory=list)
    compatibility_key: str | None = None
    case_ids: list[str] = Field(default_factory=list)
    manifest_json: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None
    screenshot_url: str | None = None
    printer_type: str | None = None
    resin: str | None = None
    layer_height_microns: int | None = None
    estimated_completion: str | None = None
    error_message: str | None = None
```

```python
_ensure_column(connection, "print_jobs", "preset_names_json", "TEXT")
_ensure_column(connection, "print_jobs", "manifest_json", "TEXT")
_ensure_column(connection, "print_jobs", "compatibility_key", "TEXT")
```

- [ ] **Step 3: Serialize and deserialize the new fields**

```python
return PrintJob(
    id=row["id"],
    job_name=row["job_name"],
    scene_id=row["scene_id"],
    print_job_id=row["print_job_id"],
    status=row["status"],
    preset=row["preset"],
    preset_names=json.loads(row["preset_names_json"]) if row["preset_names_json"] else [],
    compatibility_key=row["compatibility_key"],
    case_ids=case_ids,
    manifest_json=json.loads(row["manifest_json"]) if row["manifest_json"] else None,
    created_at=row["created_at"],
    updated_at=row["updated_at"],
    screenshot_url=row["screenshot_url"],
    printer_type=row["printer_type"],
    resin=row["resin"],
    layer_height_microns=row["layer_height_microns"],
    estimated_completion=row["estimated_completion"],
    error_message=row["error_message"],
)
```

- [ ] **Step 4: Run the print queue tests**

Run: `pytest tests/test_print_queue.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/database.py app/schemas.py tests/test_print_queue.py
git commit -m "feat: persist mixed-preset print job manifests"
```

## Task 5: Refactor Send-To-Print To Use Build Manifests

**Files:**
- Modify: `app/services/print_queue_service.py`
- Modify: `tests/test_preform_handoff.py`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Write the failing handoff tests**

```python
def test_send_to_print_groups_compatible_mixed_presets_into_one_job(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_a = tmp_path / "case-a.stl"
    case_b = tmp_path / "case-b.stl"
    case_a.write_text("solid test\nendsolid test\n", encoding="utf-8")
    case_b.write_text("solid test\nendsolid test\n", encoding="utf-8")

    row_ids = _seed_rows(
        settings,
        [
            _row_payload(case_a, case_id="CASE001", preset="Ortho Solid - Flat, No Supports", status="Ready", content_hash="hash-1"),
            _row_payload(case_b, case_id="CASE002", preset="Tooth - With Supports", status="Ready", content_hash="hash-2"),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    with patch("app.services.preform_client.PreFormClient", return_value=stub_client):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    assert len(stub_client.created_scenes) == 1
    assert stub_client.imported_models == [
        ("scene-1", str(case_a), "ortho_solid_v1"),
        ("scene-1", str(case_b), "tooth_v1"),
    ]


def test_send_to_print_rolls_back_last_case_when_validation_fails(tmp_path):
    settings = _build_settings(tmp_path)
    app = create_app(settings)
    client = TestClient(app)

    case_a = tmp_path / "case-a.stl"
    case_b = tmp_path / "case-b.stl"
    case_a.write_text("solid test\nendsolid test\n", encoding="utf-8")
    case_b.write_text("solid test\nendsolid test\n", encoding="utf-8")

    row_ids = _seed_rows(
        settings,
        [
            _row_payload(case_a, case_id="CASE001", preset="Ortho Solid - Flat, No Supports", status="Ready", content_hash="hash-1"),
            _row_payload(case_b, case_id="CASE002", preset="Die - Flat, No Supports", status="Ready", content_hash="hash-2"),
        ],
    )

    stub_client = StubPreFormClient(settings.preform_server_url)
    stub_client.validation_results = [
        {"valid": False, "errors": ["overlap"]},
        {"valid": True, "errors": []},
    ]

    with patch("app.services.preform_client.PreFormClient", return_value=stub_client):
        response = client.post("/api/uploads/rows/send-to-print", json={"row_ids": row_ids})

    assert response.status_code == 200
    assert len(list_print_jobs(settings)) == 2
```

Run: `pytest tests/test_preform_handoff.py tests/test_integration.py -q`
Expected: FAIL because batching is still preset-only and no validation rollback exists

- [ ] **Step 2: Extend the handoff stub to support layout and validation**

```python
class StubPreFormClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.created_scenes: list[tuple[str, str]] = []
        self.imported_models: list[tuple[str, str, str | None]] = []
        self.print_jobs: list[tuple[str, str]] = []
        self.layout_calls: list[str] = []
        self.validation_results: list[dict] = []
        self.closed = False

    def auto_layout(self, scene_id: str, *, allow_overlapping_supports: bool = False):
        self.layout_calls.append(scene_id)
        return {"status": "ok"}

    def validate_scene(self, scene_id: str):
        if self.validation_results:
            return self.validation_results.pop(0)
        return {"valid": True, "errors": []}
```

- [ ] **Step 3: Replace preset-only batching with build manifests**

```python
def _process_build_manifest(
    settings: "Settings",
    manifest: "BuildManifest",
    rows_by_id: dict[int, "ClassificationRow"],
    batch_number: int,
) -> dict:
    from .preform_client import PreFormClient

    def _preset_summary(preset_names: list[str]) -> str:
        if len(preset_names) == 1:
            return preset_names[0]
        return f"{preset_names[0]} + {len(preset_names) - 1} more"

    job_name = generate_job_name(datetime.now(), batch_number)
    client = PreFormClient(settings.preform_server_url)
    try:
        scene = client.create_scene(manifest.case_ids[0], job_name)
        scene_id = scene["scene_id"]
        for group in manifest.import_groups:
            for row_id in group.row_ids:
                path = get_stored_file_path(settings, row_id)
                if path is not None:
                    client.import_model(scene_id, str(path), preset=group.preform_hint)
        client.auto_layout(scene_id, allow_overlapping_supports=False)
        validation = client.validate_scene(scene_id)
        if not validation.get("valid", False):
            raise ValueError(json.dumps(validation))
        device_id = _resolve_device_id([rows_by_id[row_id] for group in manifest.import_groups for row_id in group.row_ids])
        print_result = client.send_to_printer(scene_id, device_id)
        return {
            "job_name": job_name,
            "scene_id": scene_id,
            "print_job_id": print_result.get("print_id"),
            "preset": _preset_summary(manifest.preset_names),
            "preset_names": manifest.preset_names,
            "compatibility_key": manifest.compatibility_key,
            "manifest_json": manifest.model_dump(),
            "case_ids": manifest.case_ids,
            "status": "Queued",
        }
    finally:
        client.close()
```

- [ ] **Step 4: Add whole-case rollback in the main send loop**

```python
def drop_last_case(
    manifest: BuildManifest,
    rows_by_id: dict[int, ClassificationRow],
) -> BuildManifest:
    dropped_case_id = manifest.case_ids[-1]
    next_case_ids = manifest.case_ids[:-1]
    next_import_groups: list[BuildManifestImportGroup] = []
    for group in manifest.import_groups:
        kept_row_ids = [
            row_id
            for row_id in group.row_ids
            if rows_by_id[row_id].case_id != dropped_case_id
        ]
        if kept_row_ids:
            next_import_groups.append(
                BuildManifestImportGroup(
                    preset_name=group.preset_name,
                    preform_hint=group.preform_hint,
                    row_ids=kept_row_ids,
                )
            )
    next_preset_names = [group.preset_name for group in next_import_groups]
    return BuildManifest(
        compatibility_key=manifest.compatibility_key,
        case_ids=next_case_ids,
        preset_names=next_preset_names,
        import_groups=next_import_groups,
    )


def _persist_print_job(connection, result: dict) -> None:
    connection.execute(
        """
        INSERT INTO print_jobs (
            job_name, scene_id, print_job_id, status, preset, preset_names_json,
            compatibility_key, case_ids, manifest_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (
            result["job_name"],
            result["scene_id"],
            result["print_job_id"],
            result["status"],
            result["preset"],
            json.dumps(result["preset_names"]),
            result["compatibility_key"],
            json.dumps(result["case_ids"]),
            json.dumps(result["manifest_json"]),
        ),
    )


def _mark_rows_submitted(connection, manifest: BuildManifest) -> None:
    submitted_ids = [row_id for group in manifest.import_groups for row_id in group.row_ids]
    for row_id in submitted_ids:
        connection.execute(
            "UPDATE upload_rows SET status = 'Submitted', current_event_at = ? WHERE id = ?",
            (_now_iso(), row_id),
        )


def _mark_case_exception(connection, case_id: str, reason: str) -> None:
    connection.execute(
        """
        UPDATE upload_rows
        SET status = 'Needs Review', review_required = 1, review_reason = ?
        WHERE case_id = ? AND status = 'Ready'
        """,
        (reason, case_id),
    )


manifests = plan_build_manifests(ready_rows)
for manifest in manifests:
    retry_manifest = manifest
    while retry_manifest.case_ids:
        try:
            result = _process_build_manifest(settings, retry_manifest, rows_by_id, batch_number)
            _persist_print_job(connection, result)
            _mark_rows_submitted(connection, retry_manifest)
            break
        except ValueError:
            if len(retry_manifest.case_ids) == 1:
                _mark_case_exception(connection, retry_manifest.case_ids[0], "Build validation failed")
                break
            retry_manifest = drop_last_case(retry_manifest, rows_by_id)
            continue
```

- [ ] **Step 5: Run the handoff tests**

Run: `pytest tests/test_preform_handoff.py tests/test_integration.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/print_queue_service.py tests/test_preform_handoff.py tests/test_integration.py
git commit -m "feat: drive print handoff from compatibility-aware build manifests"
```

## Task 6: Update Preview, Print Queue UI, And Docs

**Files:**
- Modify: `app/services/planning_preview.py`
- Modify: `app/static/app.js`
- Modify: `Andent/02_planning/02.02_Architecture-PreFormServer-handoff.md`
- Test: `tests/test_planning_preview.py`

- [ ] **Step 1: Write the failing preview and UI-facing tests**

```python
def test_build_batch_preview_groups_rows_by_compatibility_build():
    rows = [
        _make_row(row_id=1, case_id="P001", preset="Ortho Solid - Flat, No Supports"),
        _make_row(row_id=2, case_id="P002", preset="Tooth - With Supports"),
    ]

    result = build_batch_preview(rows)

    assert result.group_count == 1
    assert {row.predicted_group_key for row in result.rows} == {"form-4bl|precision-model-resin|100"}
```

Run: `pytest tests/test_planning_preview.py -q`
Expected: FAIL because preview still groups by preset

- [ ] **Step 2: Update preview logic to reuse the build planner**

```python
from .build_planning import plan_build_manifests


def build_batch_preview(rows: list[ClassificationRow]) -> BatchPlanPreviewResponse:
    manifests = plan_build_manifests(rows)
    row_map = {row.row_id: row for row in rows if row.row_id is not None}
    preview_rows: list[PlanPreviewRow] = []
    for manifest in manifests:
        for group in manifest.import_groups:
            for row_id in group.row_ids:
                row = row_map[row_id]
                preview_rows.append(
                    PlanPreviewRow(
                        row_id=row_id,
                        file_name=row.file_name,
                        case_id=row.case_id,
                        model_type=row.model_type,
                        preset=row.preset,
                        predicted_job_name=None,
                        predicted_group_key=manifest.compatibility_key,
                        cannot_fit=False,
                        cannot_fit_reason=None,
                        preview_available=True,
                    )
                )
    return BatchPlanPreviewResponse(rows=preview_rows, group_count=len(manifests), cannot_fit_count=0)
```

- [ ] **Step 3: Render mixed-preset jobs in the UI**

```javascript
const presetDiv = document.createElement("div");
presetDiv.className = "job-detail-item";
const presetList = (job.preset_names || []).length > 0
    ? job.preset_names.join(", ")
    : (job.preset || "-");
presetDiv.innerHTML = `<span class="job-detail-label">Presets:</span> <span class="job-detail-value">${presetList}</span>`;
detailsDiv.appendChild(presetDiv);

const compatibilityDiv = document.createElement("div");
compatibilityDiv.className = "job-detail-item";
compatibilityDiv.innerHTML = `<span class="job-detail-label">Build Profile:</span> <span class="job-detail-value">${job.compatibility_key || "-"}</span>`;
detailsDiv.appendChild(compatibilityDiv);
```

- [ ] **Step 4: Update the architecture doc**

```markdown
### Current repository note: compatibility-aware Form 4BL planning

- Rows are no longer grouped strictly by preset.
- Andent Web now builds compatibility-aware Form 4BL manifests using whole-case planning.
- Mixed presets may share a build only when they resolve to the same printer, resin, and layer-height family.
- Import into PreFormServer occurs by preset group within one build so each file still receives its correct preset hint.
```

- [ ] **Step 5: Run the preview and queue verification suite**

Run: `pytest tests/test_planning_preview.py tests/test_print_queue.py tests/test_preform_handoff.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/planning_preview.py app/static/app.js Andent/02_planning/02.02_Architecture-PreFormServer-handoff.md tests/test_planning_preview.py tests/test_print_queue.py tests/test_preform_handoff.py
git commit -m "docs: align preview and queue surfaces with form 4bl build manifests"
```

## Task 7: Final Verification Sweep

**Files:**
- Modify: none
- Test: `tests/test_preset_catalog.py`
- Test: `tests/test_build_planning.py`
- Test: `tests/test_preform_client.py`
- Test: `tests/test_preform_handoff.py`
- Test: `tests/test_print_queue.py`
- Test: `tests/test_planning_preview.py`

- [ ] **Step 1: Run the focused suite**

Run: `pytest tests/test_preset_catalog.py tests/test_build_planning.py tests/test_preform_client.py tests/test_preform_handoff.py tests/test_print_queue.py tests/test_planning_preview.py -q`
Expected: PASS

- [ ] **Step 2: Run the full repository suite**

Run: `pytest tests/ -q`
Expected: PASS

- [ ] **Step 3: Review git diff before merge**

Run: `git diff --stat`
Expected: output includes `preset_catalog.py`, `build_planning.py`, updated handoff files, updated tests, and the architecture doc

- [ ] **Step 4: Commit the verification checkpoint**

```bash
git add .
git commit -m "test: verify compatibility-aware form 4bl build planning"
```

## Self-Review

### Spec Coverage

The approved design spec requires:

1. whole-case planning
2. compatibility-aware mixed presets
3. preset-derived printer/resin/layer/support metadata
4. XY-only planning heuristic
5. largest-first seeding
6. smallest-case fillers
7. grouped import by preset hint
8. PreFormServer auto-layout plus validation
9. rollback at whole-case boundaries
10. queue and preview surfaces that reflect the new grouping

Task mapping:

1. whole-case planning: Task 3
2. compatibility-aware mixed presets: Tasks 1 and 3
3. preset-derived metadata: Task 1
4. XY-only heuristic: Task 3
5. largest-first seeding: Task 3
6. smallest-case fillers: Task 3
7. grouped import by preset hint: Task 5
8. PreFormServer auto-layout plus validation: Task 2 and Task 5
9. rollback at whole-case boundaries: Task 5
10. preview, print queue, and docs alignment: Task 6

No spec gaps remain.

### Placeholder Scan

Checked for `TBD`, `TODO`, `implement later`, `appropriate error handling`, and cross-task dangling references. None remain.

### Type Consistency

The plan consistently uses:

1. `PresetProfile`
2. `FilePrepSpec`
3. `CasePackProfile`
4. `BuildManifest`
5. `preset_names`
6. `compatibility_key`
7. `auto_layout()`
8. `validate_scene()`

Those names are used consistently across the task sequence.
