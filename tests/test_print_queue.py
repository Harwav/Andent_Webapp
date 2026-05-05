"""Phase 1: Task 5 - Print Queue Database Schema Tests (TDD)

Tests for print_jobs table, schema, CRUD helpers, and config.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _test_settings(tmp_path: Path):
    from app.config import build_settings

    return build_settings(data_dir=tmp_path, database_path=tmp_path / "andent_web.db")


def test_print_jobs_table_created_on_startup(tmp_path: Path):
    from app.database import init_db, connect

    settings = _test_settings(tmp_path)
    init_db(settings)

    with connect(settings) as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(print_jobs)").fetchall()
        }

    assert {
        "id",
        "job_name",
        "scene_id",
        "print_job_id",
        "status",
        "preset",
        "case_ids",
        "created_at",
        "updated_at",
        "screenshot_url",
        "form_file_path",
        "printer_type",
        "resin",
        "layer_height_microns",
        "estimated_completion",
        "error_message",
    }.issubset(columns)


def test_print_job_schema_validates_correctly():
    from app.schemas import PrintJob

    job = PrintJob(job_name="260421-001", preset="Ortho Solid - Flat, No Supports")

    assert job.status == "Queued"
    assert job.case_ids == []
    assert job.job_name == "260421-001"


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

    assert {
        "preset_names_json",
        "manifest_json",
        "compatibility_key",
        "estimated_density",
        "density_target",
        "hold_cutoff_at",
        "hold_reason",
        "release_reason",
        "released_by_operator",
        "validation_passed",
        "validation_errors_json",
    }.issubset(columns)


def test_print_job_crud_round_trip(tmp_path: Path):
    from app.database import (
        create_print_job,
        get_print_job_by_id,
        get_print_job_by_name,
        init_db,
        list_print_jobs,
        update_print_job,
    )
    from app.schemas import PrintJob

    settings = _test_settings(tmp_path)
    init_db(settings)

    created = create_print_job(
        settings,
        PrintJob(
            job_name="260421-001",
            scene_id="scene-123",
            preset="Ortho Solid - Flat, No Supports",
            preset_names=["Ortho Solid - Flat, No Supports", "Tooth - With Supports"],
            compatibility_key="form4b:tough2000:50",
            case_ids=["CASE001", "CASE002"],
            manifest_json={
                "compatibility_key": "form4b:tough2000:50",
                "preset_names": ["Ortho Solid - Flat, No Supports", "Tooth - With Supports"],
            },
            form_file_path=str(tmp_path / "260421-001.form"),
            estimated_density=0.35,
            density_target=0.40,
            hold_cutoff_at="2026-04-24T18:00:00",
            hold_reason="below_density_target",
            release_reason="operator_release",
            released_by_operator=True,
            validation_passed=True,
            validation_errors=[],
        ),
    )

    assert created.id is not None
    assert created.case_ids == ["CASE001", "CASE002"]
    assert created.preset_names == ["Ortho Solid - Flat, No Supports", "Tooth - With Supports"]
    assert created.compatibility_key == "form4b:tough2000:50"
    assert created.manifest_json == {
        "compatibility_key": "form4b:tough2000:50",
        "preset_names": ["Ortho Solid - Flat, No Supports", "Tooth - With Supports"],
    }
    assert created.estimated_density == 0.35
    assert created.density_target == 0.40
    assert created.hold_reason == "below_density_target"
    assert created.release_reason == "operator_release"
    assert created.released_by_operator is True
    assert created.validation_passed is True
    assert created.validation_errors == []
    assert created.form_file_path == str(tmp_path / "260421-001.form")

    by_id = get_print_job_by_id(settings, created.id)
    by_name = get_print_job_by_name(settings, "260421-001")
    jobs = list_print_jobs(settings)

    assert by_id is not None
    assert by_name is not None
    assert len(jobs) == 1
    assert by_id.job_name == created.job_name
    assert by_name.scene_id == "scene-123"
    assert by_name.form_file_path == str(tmp_path / "260421-001.form")
    assert by_id.case_ids == ["CASE001", "CASE002"]
    assert by_id.preset_names == ["Ortho Solid - Flat, No Supports", "Tooth - With Supports"]
    assert by_name.compatibility_key == "form4b:tough2000:50"
    assert jobs[0].manifest_json == {
        "compatibility_key": "form4b:tough2000:50",
        "preset_names": ["Ortho Solid - Flat, No Supports", "Tooth - With Supports"],
    }

    updated = update_print_job(
        settings,
        created.id,
        status="Printing",
        print_job_id="formlabs-123",
        error_message=None,
    )

    assert updated is not None
    assert updated.status == "Printing"
    assert updated.print_job_id == "formlabs-123"


def test_job_name_is_unique(tmp_path: Path):
    from app.database import create_print_job, init_db
    from app.schemas import PrintJob

    settings = _test_settings(tmp_path)
    init_db(settings)

    create_print_job(
        settings,
        PrintJob(job_name="260421-001", preset="Ortho Solid - Flat, No Supports"),
    )

    with pytest.raises(sqlite3.IntegrityError):
        create_print_job(
            settings,
            PrintJob(job_name="260421-001", preset="Ortho Solid - Flat, No Supports"),
        )


def test_init_db_repairs_stale_print_job_manifest_density(tmp_path: Path):
    from app.database import connect, create_print_job, get_print_job_by_id, init_db
    from app.schemas import PrintJob

    settings = _test_settings(tmp_path)
    init_db(settings)
    created = create_print_job(
        settings,
        PrintJob(
            job_name="260504-001",
            preset="Ortho Solid - Flat, No Supports",
            case_ids=["CASE-A"],
            manifest_json={
                "printer_xy_budget": 10000.0,
                "used_xy_budget": 6000.0,
                "estimated_density": 0.6,
                "import_groups": [
                    {
                        "files": [
                            {"case_id": "CASE-A", "xy_footprint_estimate": 1200.0},
                        ],
                    },
                ],
            },
            estimated_density=0.6,
        ),
    )

    init_db(settings)

    repaired = get_print_job_by_id(settings, created.id)
    assert repaired is not None
    assert repaired.estimated_density == 0.12
    assert repaired.manifest_json is not None
    assert repaired.manifest_json["used_xy_budget"] == 1200.0
    assert repaired.manifest_json["estimated_density"] == 0.12

    with connect(settings) as connection:
        stored = connection.execute(
            "SELECT manifest_json FROM print_jobs WHERE id = ?",
            (created.id,),
        ).fetchone()
    assert json.loads(stored["manifest_json"])["estimated_density"] == 0.12


def test_build_lane_lock_blocks_same_lane_until_released(tmp_path):
    from app.database import init_db, release_build_lane_lock, try_acquire_build_lane_lock

    settings = _test_settings(tmp_path)
    init_db(settings)

    assert try_acquire_build_lane_lock(settings, "device:A|form4bl|pm|100", "owner-1", "send")
    assert not try_acquire_build_lane_lock(settings, "device:A|form4bl|pm|100", "owner-2", "send")

    release_build_lane_lock(settings, "device:A|form4bl|pm|100", "owner-1")

    assert try_acquire_build_lane_lock(settings, "device:A|form4bl|pm|100", "owner-2", "send")


def test_build_lane_lock_allows_different_lanes(tmp_path):
    from app.database import init_db, try_acquire_build_lane_lock

    settings = _test_settings(tmp_path)
    init_db(settings)

    assert try_acquire_build_lane_lock(settings, "device:A|form4bl|pm|100", "owner-1", "send")
    assert try_acquire_build_lane_lock(settings, "device:B|form4bl|pm|100", "owner-2", "send")
    assert try_acquire_build_lane_lock(settings, "group:Form 4B|lt-clear|100", "owner-3", "send")


def test_build_lane_lock_replaces_expired_lock(tmp_path):
    from app.database import init_db, try_acquire_build_lane_lock

    settings = _test_settings(tmp_path)
    init_db(settings)
    old_now = datetime.now(timezone.utc) - timedelta(hours=3)

    assert try_acquire_build_lane_lock(
        settings,
        "device:A|form4bl|pm|100",
        "owner-1",
        "send",
        now=old_now,
    )

    assert try_acquire_build_lane_lock(settings, "device:A|form4bl|pm|100", "owner-2", "send")


def test_case_ids_are_persisted_as_json(tmp_path: Path):
    from app.database import create_print_job, get_print_job_by_id, init_db
    from app.schemas import PrintJob

    settings = _test_settings(tmp_path)
    init_db(settings)

    created = create_print_job(
        settings,
        PrintJob(
            job_name="260421-002",
            preset="Ortho Solid - Flat, No Supports",
            case_ids=["CASE001", "CASE002"],
        ),
    )

    loaded = get_print_job_by_id(settings, created.id)
    assert loaded is not None
    assert loaded.case_ids == ["CASE001", "CASE002"]

    with sqlite3.connect(settings.database_path) as connection:
        raw_case_ids = connection.execute(
            "SELECT case_ids FROM print_jobs WHERE id = ?",
            (created.id,),
        ).fetchone()[0]

    assert raw_case_ids == '["CASE001", "CASE002"]'


def test_config_loads_formlabs_api_token(monkeypatch: pytest.MonkeyPatch):
    from app.config import build_settings

    monkeypatch.setenv("FORMLABS_API_TOKEN", "test-token-123")
    settings = build_settings()

    assert settings.formlabs_api_token == "test-token-123"


def test_coalesce_manifests_by_lane_key_merges_same_lane(tmp_path):
    """Two manifests with same lane key should merge into one."""
    from app.schemas import BuildManifest, BuildManifestImportGroup, FilePrepSpec

    def make_file(row_id, case_id):
        return FilePrepSpec(
            row_id=row_id,
            case_id=case_id,
            file_name=f"case{row_id}.stl",
            file_path=f"/tmp/case{row_id}.stl",
            preset_name="Ortho Solid - Flat, No Supports",
            compatibility_key="form-4bl|precision-model-v1|100",
            xy_footprint_estimate=1000.0,
            support_inflation_factor=1.0,
        )

    # Two manifests with same lane configuration (same printer/material/layer)
    manifest_a = BuildManifest(
        compatibility_key="form-4bl|precision-model-v1|100",
        case_ids=["CASE001", "CASE002", "CASE003"],
        preset_names=["Ortho Solid - Flat, No Supports"],
        import_groups=[
            BuildManifestImportGroup(
                preset_name="Ortho Solid - Flat, No Supports",
                preform_hint="ortho_solid_v1",
                row_ids=[1, 2],
                files=[make_file(1, "CASE001"), make_file(2, "CASE002")],
            ),
        ],
        printer_group="Form 4BL",
        material_code="FLPMBE01",
        material_label="Precision Model V1",
        layer_thickness_mm=0.1,
        print_setting="DEFAULT",
        estimated_density=0.45,
    )

    manifest_b = BuildManifest(
        compatibility_key="form-4bl|precision-model-v1|100",
        case_ids=["CASE004", "CASE005"],
        preset_names=["Ortho Solid - Flat, No Supports"],
        import_groups=[
            BuildManifestImportGroup(
                preset_name="Ortho Solid - Flat, No Supports",
                preform_hint="ortho_solid_v1",
                row_ids=[3, 4],
                files=[make_file(3, "CASE004"), make_file(4, "CASE005")],
            ),
        ],
        printer_group="Form 4BL",
        material_code="FLPMBE01",
        material_label="Precision Model V1",
        layer_thickness_mm=0.1,
        print_setting="DEFAULT",
        estimated_density=0.25,
    )

    from app.services.print_queue_service import _coalesce_manifests_by_lane_key

    coalesced = _coalesce_manifests_by_lane_key([manifest_a, manifest_b])

    # Should be 1 coalesced manifest, not 2
    assert len(coalesced) == 1, f"Expected 1 coalesced manifest, got {len(coalesced)}"

    result = coalesced[0]
    # All case_ids should be present
    assert set(result.case_ids) == {"CASE001", "CASE002", "CASE003", "CASE004", "CASE005"}
    # All row_ids should be present
    all_row_ids = [f.row_id for g in result.import_groups for f in g.files]
    assert set(all_row_ids) == {1, 2, 3, 4}
    # All import_groups preserved
    assert len(result.import_groups) == 2


def test_coalesce_manifests_by_lane_key_keeps_different_lanes_separate(tmp_path):
    """Manifests with different lane keys should not merge."""
    from app.schemas import BuildManifest, BuildManifestImportGroup, FilePrepSpec

    def make_file(row_id, case_id, preset_name, compat_key):
        return FilePrepSpec(
            row_id=row_id,
            case_id=case_id,
            file_name=f"case{row_id}.stl",
            file_path=f"/tmp/case{row_id}.stl",
            preset_name=preset_name,
            compatibility_key=compat_key,
            xy_footprint_estimate=1000.0,
            support_inflation_factor=1.0,
        )

    manifest_form4bl = BuildManifest(
        compatibility_key="form-4bl|precision-model-v1|100",
        case_ids=["CASE001"],
        preset_names=["Ortho Solid - Flat, No Supports"],
        import_groups=[
            BuildManifestImportGroup(
                preset_name="Ortho Solid - Flat, No Supports",
                preform_hint="ortho_solid_v1",
                row_ids=[1],
                files=[make_file(1, "CASE001", "Ortho Solid - Flat, No Supports", "form-4bl|precision-model-v1|100")],
            ),
        ],
        printer_group="Form 4BL",
        material_code="FLPMBE01",
        material_label="Precision Model V1",
        layer_thickness_mm=0.1,
        print_setting="DEFAULT",
        estimated_density=0.5,
    )

    manifest_form4b = BuildManifest(
        compatibility_key="form-4b|tough2000|50",
        case_ids=["CASE002"],
        preset_names=["Tough 2000 V2"],
        import_groups=[
            BuildManifestImportGroup(
                preset_name="Tough 2000 V2",
                preform_hint="tough_v2",
                row_ids=[2],
                files=[make_file(2, "CASE002", "Tough 2000 V2", "form-4b|tough2000|50")],
            ),
        ],
        printer_group="Form 4B",
        material_code="FLTBLK01",
        material_label="Tough 2000 V2",
        layer_thickness_mm=0.05,
        print_setting="DEFAULT",
        estimated_density=0.5,
    )

    from app.services.print_queue_service import _coalesce_manifests_by_lane_key

    coalesced = _coalesce_manifests_by_lane_key([manifest_form4bl, manifest_form4b])

    # Should remain 2 separate manifests (different lane keys)
    assert len(coalesced) == 2


def test_coalesce_manifests_passes_through_non_planned_manifests():
    """Non-planned manifests must pass through so the dispatch loop can route them to manual review."""
    from app.schemas import BuildManifest, BuildManifestImportGroup, FilePrepSpec
    from app.services.print_queue_service import _coalesce_manifests_by_lane_key

    planned = BuildManifest(
        compatibility_key="form-4bl|precision-model-v1|100",
        case_ids=["CASE-PLANNED"],
        preset_names=["Ortho Solid - Flat, No Supports"],
        import_groups=[
            BuildManifestImportGroup(
                preset_name="Ortho Solid - Flat, No Supports",
                preform_hint="ortho_solid_v1",
                row_ids=[1],
                files=[FilePrepSpec(
                    row_id=1, case_id="CASE-PLANNED",
                    file_name="planned.stl", file_path="/tmp/planned.stl",
                    preset_name="Ortho Solid - Flat, No Supports",
                    compatibility_key="form-4bl|precision-model-v1|100",
                    xy_footprint_estimate=1000.0, support_inflation_factor=1.0,
                )],
            ),
        ],
        printer_group="Form 4BL",
        material_code="FLPMBE01",
        material_label="Precision Model V1",
        layer_thickness_mm=0.1,
        print_setting="DEFAULT",
        estimated_density=0.3,
        planning_status="planned",
    )

    non_planned = BuildManifest(
        compatibility_key="form-4bl|precision-model-v1|100",
        case_ids=["CASE-BLOCKED"],
        preset_names=[],
        import_groups=[],
        printer_group="Form 4BL",
        material_code="FLPMBE01",
        material_label="Precision Model V1",
        layer_thickness_mm=0.1,
        print_setting="DEFAULT",
        estimated_density=0.0,
        planning_status="non_plannable",
        non_plannable_reason="incompatible_case_presets",
    )

    coalesced = _coalesce_manifests_by_lane_key([planned, non_planned])

    # Both manifests must be returned — non-planned must not be silently dropped
    assert len(coalesced) == 2
    statuses = {m.planning_status for m in coalesced}
    assert "planned" in statuses
    assert "non_plannable" in statuses


def test_coalesce_manifests_recomputes_estimated_density():
    """Merged manifest density must reflect combined used_xy_budget, not just the first manifest."""
    from app.schemas import BuildManifest, BuildManifestImportGroup, FilePrepSpec
    from app.services.print_queue_service import _coalesce_manifests_by_lane_key

    def make_file(row_id, case_id):
        return FilePrepSpec(
            row_id=row_id, case_id=case_id,
            file_name=f"{case_id}.stl", file_path=f"/tmp/{case_id}.stl",
            preset_name="Ortho Solid - Flat, No Supports",
            compatibility_key="form-4bl|precision-model-v1|100",
            xy_footprint_estimate=1000.0, support_inflation_factor=1.0,
        )

    printer_xy_budget = 100_000.0

    manifest_a = BuildManifest(
        compatibility_key="form-4bl|precision-model-v1|100",
        case_ids=["CASE-A"],
        preset_names=["Ortho Solid - Flat, No Supports"],
        import_groups=[BuildManifestImportGroup(
            preset_name="Ortho Solid - Flat, No Supports",
            preform_hint="ortho_solid_v1",
            row_ids=[1],
            files=[make_file(1, "CASE-A")],
        )],
        printer_group="Form 4BL",
        material_code="FLPMBE01",
        material_label="Precision Model V1",
        layer_thickness_mm=0.1,
        print_setting="DEFAULT",
        printer_xy_budget=printer_xy_budget,
        used_xy_budget=45_000.0,
        estimated_density=0.45,
    )

    manifest_b = BuildManifest(
        compatibility_key="form-4bl|precision-model-v1|100",
        case_ids=["CASE-B"],
        preset_names=["Ortho Solid - Flat, No Supports"],
        import_groups=[BuildManifestImportGroup(
            preset_name="Ortho Solid - Flat, No Supports",
            preform_hint="ortho_solid_v1",
            row_ids=[2],
            files=[make_file(2, "CASE-B")],
        )],
        printer_group="Form 4BL",
        material_code="FLPMBE01",
        material_label="Precision Model V1",
        layer_thickness_mm=0.1,
        print_setting="DEFAULT",
        printer_xy_budget=printer_xy_budget,
        used_xy_budget=25_000.0,
        estimated_density=0.25,
    )

    coalesced = _coalesce_manifests_by_lane_key([manifest_a, manifest_b])

    assert len(coalesced) == 1
    result = coalesced[0]
    assert result.used_xy_budget == 70_000.0
    assert abs(result.estimated_density - 0.70) < 0.001


def test_coalesce_manifests_keeps_originals_when_merge_exceeds_budget():
    """If merged footprint exceeds printer_xy_budget, keep the originals for individual dispatch."""
    from app.schemas import BuildManifest, BuildManifestImportGroup, FilePrepSpec
    from app.services.print_queue_service import _coalesce_manifests_by_lane_key

    def make_file(row_id, case_id):
        return FilePrepSpec(
            row_id=row_id, case_id=case_id,
            file_name=f"{case_id}.stl", file_path=f"/tmp/{case_id}.stl",
            preset_name="Ortho Solid - Flat, No Supports",
            compatibility_key="form-4bl|precision-model-v1|100",
            xy_footprint_estimate=1000.0, support_inflation_factor=1.0,
        )

    printer_xy_budget = 100_000.0

    manifest_a = BuildManifest(
        compatibility_key="form-4bl|precision-model-v1|100",
        case_ids=["CASE-BIG-A"],
        preset_names=["Ortho Solid - Flat, No Supports"],
        import_groups=[BuildManifestImportGroup(
            preset_name="Ortho Solid - Flat, No Supports",
            preform_hint="ortho_solid_v1",
            row_ids=[1],
            files=[make_file(1, "CASE-BIG-A")],
        )],
        printer_group="Form 4BL",
        material_code="FLPMBE01",
        material_label="Precision Model V1",
        layer_thickness_mm=0.1,
        print_setting="DEFAULT",
        printer_xy_budget=printer_xy_budget,
        used_xy_budget=70_000.0,
        estimated_density=0.70,
    )

    manifest_b = BuildManifest(
        compatibility_key="form-4bl|precision-model-v1|100",
        case_ids=["CASE-BIG-B"],
        preset_names=["Ortho Solid - Flat, No Supports"],
        import_groups=[BuildManifestImportGroup(
            preset_name="Ortho Solid - Flat, No Supports",
            preform_hint="ortho_solid_v1",
            row_ids=[2],
            files=[make_file(2, "CASE-BIG-B")],
        )],
        printer_group="Form 4BL",
        material_code="FLPMBE01",
        material_label="Precision Model V1",
        layer_thickness_mm=0.1,
        print_setting="DEFAULT",
        printer_xy_budget=printer_xy_budget,
        used_xy_budget=50_000.0,
        estimated_density=0.50,
    )

    coalesced = _coalesce_manifests_by_lane_key([manifest_a, manifest_b])

    # Combined 120k > 100k budget — keep both originals, don't merge
    assert len(coalesced) == 2
    case_id_sets = [set(m.case_ids) for m in coalesced]
    assert {"CASE-BIG-A"} in case_id_sets
    assert {"CASE-BIG-B"} in case_id_sets
