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


def test_plan_build_manifests_uses_smallest_fitting_cases_as_fillers():
    rows = [
        _row(1, "CASE-L", "Ortho Solid - Flat, No Supports", 200.0, 130.0),
        _row(2, "CASE-M", "Ortho Solid - Flat, No Supports", 60.0, 50.0),
        _row(3, "CASE-S1", "Ortho Solid - Flat, No Supports", 40.0, 25.0),
        _row(4, "CASE-S2", "Ortho Solid - Flat, No Supports", 50.0, 40.0),
    ]

    manifests = plan_build_manifests(rows)

    assert manifests[0].case_ids == ["CASE-L", "CASE-S1", "CASE-S2"]
