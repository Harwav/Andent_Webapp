"""Phase 1: Task 3 - Compatibility-aware build planning tests (TDD)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import build_settings
from app.database import init_db, persist_upload_session
from app.schemas import ClassificationRow, DimensionSummary
from app.services.build_planning import plan_build_manifests
from app.services.preset_catalog import PRESET_CATALOG, PresetProfile
from app.services.print_queue_service import generate_job_name

_DEFAULT_FILE_PATH = object()


def _row(
    row_id: int,
    case_id: str | None,
    preset: str | None,
    *,
    status: str = "Ready",
    x: float = 40.0,
    y: float = 30.0,
    file_path: str | None | object = _DEFAULT_FILE_PATH,
) -> ClassificationRow:
    if file_path is _DEFAULT_FILE_PATH:
        resolved_file_path = f"C:/cases/{case_id}/{row_id}.stl" if case_id is not None else None
    else:
        resolved_file_path = file_path
    return ClassificationRow(
        row_id=row_id,
        file_name=f"row-{row_id}.stl",
        case_id=case_id,
        preset=preset,
        confidence="high",
        status=status,
        dimensions=DimensionSummary(x_mm=x, y_mm=y, z_mm=10.0),
        file_path=resolved_file_path,
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
                    "order": 2,
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
                    "order": 0,
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
                    "order": 1,
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


def test_plan_build_manifests_uses_persisted_stored_paths_in_file_specs(tmp_path):
    settings = build_settings(
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "andent_web.db",
    )
    init_db(settings)
    stored_file = tmp_path / "persisted-die.stl"
    stored_file.write_text("solid test\nendsolid test\n", encoding="utf-8")

    persisted_rows = persist_upload_session(
        settings,
        "session-1",
        [
            {
                "file_name": stored_file.name,
                "stored_path": str(stored_file),
                "content_hash": "hash-1",
                "thumbnail_svg": None,
                "case_id": "CASE-PERSISTED",
                "model_type": "Die",
                "preset": "Die",
                "confidence": "high",
                "status": "Ready",
                "dimension_x_mm": 10.0,
                "dimension_y_mm": 10.0,
                "dimension_z_mm": 5.0,
                "volume_ml": 0.5,
                "review_required": False,
                "review_reason": None,
            }
        ],
    )

    manifests = plan_build_manifests(persisted_rows)

    manifest_file = manifests[0].import_groups[0].files[0]
    assert manifest_file.file_path == str(stored_file)
    assert manifest_file.file_path != persisted_rows[0].file_url


def test_plan_build_manifests_canonicalizes_alias_and_profile_preset_names():
    rows = [
        _row(1, "CASE-MIXED", "Die", file_path="C:/cases/case-mixed/die-legacy.stl"),
        _row(
            2,
            "CASE-MIXED",
            "Die - Flat, No Supports",
            x=20.0,
            y=20.0,
            file_path="C:/cases/case-mixed/die-canonical.stl",
        ),
    ]

    manifests = plan_build_manifests(rows)

    assert len(manifests) == 1
    assert manifests[0].preset_names == ["Die - Flat, No Supports"]
    assert [group.preset_name for group in manifests[0].import_groups] == [
        "Die - Flat, No Supports"
    ]
    assert [
        file_spec.preset_name
        for file_spec in manifests[0].import_groups[0].files
    ] == [
        "Die - Flat, No Supports",
        "Die - Flat, No Supports",
    ]
