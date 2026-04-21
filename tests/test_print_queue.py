"""Phase 1: Task 5 - Print Queue Database Schema Tests (TDD)

Tests for print_jobs table, schema, CRUD helpers, and config.
"""

from __future__ import annotations

import sqlite3
import sys
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
            case_ids=["CASE001", "CASE002"],
        ),
    )

    assert created.id is not None
    assert created.case_ids == ["CASE001", "CASE002"]

    by_id = get_print_job_by_id(settings, created.id)
    by_name = get_print_job_by_name(settings, "260421-001")
    jobs = list_print_jobs(settings)

    assert by_id is not None
    assert by_name is not None
    assert len(jobs) == 1
    assert by_id.job_name == created.job_name
    assert by_name.scene_id == "scene-123"
    assert by_id.case_ids == ["CASE001", "CASE002"]

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
