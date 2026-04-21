"""Phase 1: Task 3 - Compatibility-aware build planning tests (TDD)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.schemas import ClassificationRow, DimensionSummary
from app.services.build_planning import plan_build_manifests
from app.services.preset_catalog import PRESET_CATALOG, PresetProfile
from app.services.print_queue_service import generate_job_name


def _row(
    row_id: int,
    case_id: str | None,
    preset: str | None,
    *,
    status: str = "Ready",
    x: float = 40.0,
    y: float = 30.0,
    file_path: str | None = None,
) -> ClassificationRow:
    return ClassificationRow(
        row_id=row_id,
        file_name=f"row-{row_id}.stl",
        case_id=case_id,
        preset=preset,
        confidence="high",
        status=status,
        dimensions=DimensionSummary(x_mm=x, y_mm=y, z_mm=10.0),
        file_path=file_path,
    )


def test_generate_job_name_format():
    """Job name should be in YYMMDD-NNN format."""
    date = datetime(2026, 4, 21)
    job_name = generate_job_name(date, 1)
    assert job_name == "260421-001"


def test_generate_job_name_double_digit():
    """Job name should handle double digit batch numbers."""
    date = datetime(2026, 4, 21)
    job_name = generate_job_name(date, 12)
    assert job_name == "260421-012"


def test_generate_job_name_triple_digit():
    """Job name should handle triple digit batch numbers."""
    date = datetime(2026, 4, 21)
    job_name = generate_job_name(date, 123)
    assert job_name == "260421-123"


def test_plan_build_manifests_splits_incompatible_compatibility_groups(monkeypatch):
    monkeypatch.setitem(
        PRESET_CATALOG,
        "Experimental Preset",
        PresetProfile(
            preset_name="Experimental Preset",
            printer="Form 4BL",
            resin="Precision Model Resin",
            layer_height_microns=50,
            requires_supports=False,
            preform_hint="experimental_v1",
        ),
    )

    rows = [
        _row(1, "CASE-ORTHO", "Ortho Solid - Flat, No Supports"),
        _row(2, "CASE-EXPERIMENT", "Experimental Preset"),
    ]

    manifests = plan_build_manifests(rows)

    assert len(manifests) == 2
    assert {tuple(manifest.case_ids) for manifest in manifests} == {
        ("CASE-ORTHO",),
        ("CASE-EXPERIMENT",),
    }


def test_plan_build_manifests_ignores_rows_missing_ready_case_or_preset():
    rows = [
        _row(1, "CASE-READY", "Ortho Solid - Flat, No Supports"),
        _row(2, "CASE-CHECK", "Tooth - With Supports", status="Check"),
        _row(3, None, "Die - Flat, No Supports"),
        _row(4, "CASE-NOPRESET", None),
    ]

    manifests = plan_build_manifests(rows)

    assert len(manifests) == 1
    assert manifests[0].case_ids == ["CASE-READY"]
    assert manifests[0].preset_names == ["Ortho Solid - Flat, No Supports"]


def test_plan_build_manifests_groups_imports_by_preset_with_preform_hints():
    rows = [
        _row(
            1,
            "CASE-1",
            "Tooth - With Supports",
            file_path="C:/cases/case-1/tooth-1.stl",
        ),
        _row(
            2,
            "CASE-1",
            "Tooth - With Supports",
            x=20.0,
            y=20.0,
            file_path="C:/cases/case-1/tooth-2.stl",
        ),
        _row(
            3,
            "CASE-2",
            "Die - Flat, No Supports",
            file_path="C:/cases/case-2/die.stl",
        ),
    ]

    manifests = plan_build_manifests(rows)

    assert len(manifests) == 1
    assert manifests[0].preset_names == [
        "Die - Flat, No Supports",
        "Tooth - With Supports",
    ]
    assert [group.model_dump() for group in manifests[0].import_groups] == [
        {
            "preset_name": "Die - Flat, No Supports",
            "preform_hint": "die_v1",
            "row_ids": [3],
            "files": [
                {
                    "row_id": 3,
                    "case_id": "CASE-2",
                    "file_name": "row-3.stl",
                    "file_path": "C:/cases/case-2/die.stl",
                    "preset_name": "Die - Flat, No Supports",
                    "compatibility_key": "form-4bl|precision-model-resin|100",
                    "xy_footprint_estimate": 1200.0,
                    "support_inflation_factor": 1.0,
                    "order": 0,
                    "preform_hint": "die_v1",
                }
            ],
        },
        {
            "preset_name": "Tooth - With Supports",
            "preform_hint": "tooth_v1",
            "row_ids": [1, 2],
            "files": [
                {
                    "row_id": 1,
                    "case_id": "CASE-1",
                    "file_name": "row-1.stl",
                    "file_path": "C:/cases/case-1/tooth-1.stl",
                    "preset_name": "Tooth - With Supports",
                    "compatibility_key": "form-4bl|precision-model-resin|100",
                    "xy_footprint_estimate": 1200.0,
                    "support_inflation_factor": 1.18,
                    "order": 1,
                    "preform_hint": "tooth_v1",
                },
                {
                    "row_id": 2,
                    "case_id": "CASE-1",
                    "file_name": "row-2.stl",
                    "file_path": "C:/cases/case-1/tooth-2.stl",
                    "preset_name": "Tooth - With Supports",
                    "compatibility_key": "form-4bl|precision-model-resin|100",
                    "xy_footprint_estimate": 400.0,
                    "support_inflation_factor": 1.18,
                    "order": 2,
                    "preform_hint": "tooth_v1",
                },
            ],
        },
    ]


def test_plan_build_manifests_skips_unknown_presets_without_aborting_valid_cases():
    rows = [
        _row(1, "CASE-VALID", "Ortho Solid - Flat, No Supports"),
        _row(2, "CASE-UNKNOWN", "Unknown Preset"),
        _row(3, "CASE-VALID-2", "Die - Flat, No Supports"),
    ]

    manifests = plan_build_manifests(rows)

    assert len(manifests) == 1
    assert manifests[0].case_ids == ["CASE-VALID", "CASE-VALID-2"]
    assert manifests[0].preset_names == [
        "Die - Flat, No Supports",
        "Ortho Solid - Flat, No Supports",
    ]


def test_plan_build_manifests_emits_harder_compatibility_group_before_easier_one(
    monkeypatch,
):
    monkeypatch.setitem(
        PRESET_CATALOG,
        "Experimental Preset",
        PresetProfile(
            preset_name="Experimental Preset",
            printer="Form 4BL",
            resin="Precision Model Resin",
            layer_height_microns=50,
            requires_supports=False,
            preform_hint="experimental_v1",
        ),
    )

    rows = [
        _row(1, "CASE-EASY", "Experimental Preset", x=20.0, y=20.0),
        _row(2, "CASE-HARD", "Ortho Solid - Flat, No Supports", x=150.0, y=120.0),
    ]

    manifests = plan_build_manifests(rows)

    assert [manifest.case_ids for manifest in manifests] == [
        ["CASE-HARD"],
        ["CASE-EASY"],
    ]
