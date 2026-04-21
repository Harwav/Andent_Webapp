from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.schemas import ClassificationRow, DimensionSummary
from app.services.build_planning import plan_build_manifests
from app.services.preset_catalog import PRESET_CATALOG, PresetProfile

_DEFAULT_DIMENSIONS = object()


def _row(
    row_id: int | None,
    case_id: str,
    preset: str,
    x: float,
    y: float,
    *,
    dimensions: DimensionSummary | None | object = _DEFAULT_DIMENSIONS,
    file_path: str | None = None,
) -> ClassificationRow:
    return ClassificationRow(
        row_id=row_id,
        file_name=f"{case_id}-{row_id}.stl",
        case_id=case_id,
        preset=preset,
        confidence="high",
        status="Ready",
        dimensions=(
            DimensionSummary(x_mm=x, y_mm=y, z_mm=10.0)
            if dimensions is _DEFAULT_DIMENSIONS
            else dimensions
        ),
        file_path=file_path,
    )


def test_plan_build_manifests_preserves_case_cohesion():
    """Planner keeps all rows from the same case together in one build."""
    rows = [
        _row(1, "CASE-1", "Ortho Solid - Flat, No Supports", 80.0, 70.0),
        _row(2, "CASE-1", "Tooth - With Supports", 40.0, 30.0),
        _row(3, "CASE-2", "Die - Flat, No Supports", 70.0, 60.0),
    ]

    manifests = plan_build_manifests(rows)

    assert len(manifests) == 1
    assert manifests[0].case_ids == ["CASE-1", "CASE-2"]


def test_plan_build_manifests_allows_mixed_compatible_presets_to_share_one_build():
    """Compatible presets may be planned into the same build manifest."""
    rows = [
        _row(1, "CASE-1", "Ortho Solid - Flat, No Supports", 60.0, 50.0),
        _row(2, "CASE-2", "Tooth - With Supports", 35.0, 35.0),
    ]

    manifests = plan_build_manifests(rows)

    assert len(manifests) == 1
    assert manifests[0].case_ids == ["CASE-1", "CASE-2"]
    assert manifests[0].preset_names == [
        "Ortho Solid - Flat, No Supports",
        "Tooth - With Supports",
    ]


def test_plan_build_manifests_uses_smallest_case_fillers_after_large_cases_do_not_fit():
    """Once the next-largest case does not fit, the planner fills with smaller cases."""
    rows = [
        _row(1, "CASE-L", "Ortho Solid - Flat, No Supports", 200.0, 130.0),
        _row(2, "CASE-M", "Ortho Solid - Flat, No Supports", 70.0, 50.0),
        _row(3, "CASE-S1", "Ortho Solid - Flat, No Supports", 40.0, 25.0),
        _row(4, "CASE-S2", "Ortho Solid - Flat, No Supports", 50.0, 40.0),
    ]

    manifests = plan_build_manifests(rows)

    assert manifests[0].case_ids == ["CASE-L", "CASE-S1", "CASE-S2"]


def test_plan_build_manifests_keeps_row_id_validation_local_to_case_profiles():
    rows = [
        _row(1, "CASE-INCOMPLETE", "Ortho Solid - Flat, No Supports", 60.0, 50.0),
        _row(None, "CASE-INCOMPLETE", "Ortho Solid - Flat, No Supports", 20.0, 20.0),
        _row(3, "CASE-VALID", "Ortho Solid - Flat, No Supports", 40.0, 30.0),
    ]

    manifests = plan_build_manifests(rows)

    assert len(manifests) == 1
    assert manifests[0].case_ids == ["CASE-VALID"]


def test_plan_build_manifests_prefers_next_largest_fit_before_small_fillers():
    rows = [
        _row(1, "CASE-15K", "Ortho Solid - Flat, No Supports", 150.0, 100.0),
        _row(2, "CASE-14K", "Ortho Solid - Flat, No Supports", 140.0, 100.0),
        _row(3, "CASE-1K", "Ortho Solid - Flat, No Supports", 40.0, 25.0),
    ]

    manifests = plan_build_manifests(rows)

    assert [manifest.case_ids for manifest in manifests] == [
        ["CASE-15K", "CASE-14K"],
        ["CASE-1K"],
    ]


def test_plan_build_manifests_marks_oversized_single_case_as_non_plannable():
    rows = [
        _row(1, "CASE-HUGE", "Ortho Solid - Flat, No Supports", 200.0, 150.0),
    ]

    manifests = plan_build_manifests(rows)

    assert len(manifests) == 1
    assert manifests[0].case_ids == ["CASE-HUGE"]
    assert manifests[0].planning_status == "non_plannable"
    assert manifests[0].non_plannable_reason == "oversized_case"
    assert manifests[0].import_groups == []


def test_plan_build_manifests_marks_incompatible_presets_within_one_case_as_non_plannable(
    monkeypatch,
):
    monkeypatch.setitem(
        PRESET_CATALOG,
        "Experimental Preset",
        PresetProfile(
            preset_name="Experimental Preset",
            printer="Form 4BL",
            resin="Draft Resin",
            layer_height_microns=100,
            requires_supports=False,
            preform_hint="experimental_v1",
        ),
    )

    rows = [
        _row(1, "CASE-MIXED", "Ortho Solid - Flat, No Supports", 60.0, 50.0),
        _row(2, "CASE-MIXED", "Experimental Preset", 40.0, 30.0),
    ]

    manifests = plan_build_manifests(rows)

    assert len(manifests) == 1
    assert manifests[0].case_ids == ["CASE-MIXED"]
    assert manifests[0].planning_status == "non_plannable"
    assert manifests[0].non_plannable_reason == "incompatible_case_presets"
    assert manifests[0].import_groups == []


def test_plan_build_manifests_marks_missing_dimensions_as_non_plannable():
    rows = [
        _row(
            1,
            "CASE-NODIMS",
            "Ortho Solid - Flat, No Supports",
            60.0,
            50.0,
            dimensions=None,
        ),
    ]

    manifests = plan_build_manifests(rows)

    assert len(manifests) == 1
    assert manifests[0].case_ids == ["CASE-NODIMS"]
    assert manifests[0].planning_status == "non_plannable"
    assert manifests[0].non_plannable_reason == "missing_dimensions"
    assert manifests[0].import_groups == []


def test_plan_build_manifests_skips_unknown_presets_even_when_dimensions_are_missing():
    rows = [
        _row(1, "CASE-VALID", "Ortho Solid - Flat, No Supports", 60.0, 50.0),
        _row(
            2,
            "CASE-UNKNOWN",
            "Unknown Preset",
            40.0,
            30.0,
            dimensions=None,
        ),
        _row(3, "CASE-VALID-2", "Die - Flat, No Supports", 40.0, 30.0),
    ]

    manifests = plan_build_manifests(rows)

    assert len(manifests) == 1
    assert manifests[0].case_ids == ["CASE-VALID", "CASE-VALID-2"]
    assert manifests[0].planning_status == "planned"


def test_plan_build_manifests_preserves_selected_case_priority_in_file_order():
    rows = [
        _row(10, "CASE-Z-HARD", "Die - Flat, No Supports", 80.0, 70.0),
        _row(11, "CASE-Z-HARD", "Die - Flat, No Supports", 40.0, 20.0),
        _row(20, "CASE-A-EASY", "Die - Flat, No Supports", 20.0, 20.0),
    ]

    manifests = plan_build_manifests(rows)

    assert manifests[0].case_ids == ["CASE-Z-HARD", "CASE-A-EASY"]
    ordered_files = sorted(
        manifests[0].import_groups[0].files,
        key=lambda spec: spec.order,
    )
    assert [spec.row_id for spec in ordered_files] == [10, 11, 20]
