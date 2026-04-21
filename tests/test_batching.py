"""Phase 1: Task 2 - Batching Logic Tests (TDD)

Tests for grouping Ready cases by preset and generating job names.
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.schemas import ClassificationRow
from app.services.print_queue_service import batch_cases_by_preset, generate_job_name


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


def test_batch_cases_by_preset_empty():
    """Empty list should return empty dict."""
    result = batch_cases_by_preset([])
    assert result == {}


def test_batch_cases_by_preset_single():
    """Single case should return one batch."""
    row = ClassificationRow(
        row_id=1,
        file_name="test.stl",
        preset="Ortho Solid - Flat, No Supports",
        confidence="high",
        status="Ready",
    )
    result = batch_cases_by_preset([row])
    assert len(result) == 1
    assert "Ortho Solid - Flat, No Supports" in result
    assert result["Ortho Solid - Flat, No Supports"] == [row]


def test_batch_cases_by_preset_multiple_same():
    """Multiple cases with same preset should group together."""
    rows = [
        ClassificationRow(
            row_id=1,
            file_name="test1.stl",
            preset="Ortho Solid - Flat, No Supports",
            confidence="high",
            status="Ready",
        ),
        ClassificationRow(
            row_id=2,
            file_name="test2.stl",
            preset="Ortho Solid - Flat, No Supports",
            confidence="high",
            status="Ready",
        ),
    ]
    result = batch_cases_by_preset(rows)
    assert len(result) == 1
    assert len(result["Ortho Solid - Flat, No Supports"]) == 2


def test_batch_cases_by_preset_multiple_different():
    """Cases with different presets should be in separate batches."""
    rows = [
        ClassificationRow(
            row_id=1,
            file_name="test1.stl",
            preset="Ortho Solid - Flat, No Supports",
            confidence="high",
            status="Ready",
        ),
        ClassificationRow(
            row_id=2,
            file_name="test2.stl",
            preset="Tooth - With Supports",
            confidence="high",
            status="Ready",
        ),
        ClassificationRow(
            row_id=3,
            file_name="test3.stl",
            preset="Die - Flat, No Supports",
            confidence="high",
            status="Ready",
        ),
    ]
    result = batch_cases_by_preset(rows)
    assert len(result) == 3
    assert "Ortho Solid - Flat, No Supports" in result
    assert "Tooth - With Supports" in result
    assert "Die - Flat, No Supports" in result


def test_batch_cases_by_preset_none_excluded():
    """Cases with None preset should be excluded."""
    rows = [
        ClassificationRow(
            row_id=1,
            file_name="test1.stl",
            preset="Ortho Solid - Flat, No Supports",
            confidence="high",
            status="Ready",
        ),
        ClassificationRow(
            row_id=2,
            file_name="test2.stl",
            preset=None,
            confidence="low",
            status="Needs Review",
        ),
    ]
    result = batch_cases_by_preset(rows)
    assert len(result) == 1
    assert None not in result


def test_batch_cases_by_preset_only_ready_rows():
    """Only Ready rows should be included in batches."""
    rows = [
        ClassificationRow(
            row_id=1,
            file_name="test1.stl",
            preset="Ortho Solid - Flat, No Supports",
            confidence="high",
            status="Ready",
        ),
        ClassificationRow(
            row_id=2,
            file_name="test2.stl",
            preset="Ortho Solid - Flat, No Supports",
            confidence="medium",
            status="Check",
        ),
    ]
    result = batch_cases_by_preset(rows)
    assert len(result) == 1
    assert result["Ortho Solid - Flat, No Supports"] == [rows[0]]


def test_batch_cases_by_preset_duplicate_rows_deduped():
    """Duplicate rows should not be added twice to the same batch."""
    row = ClassificationRow(
        row_id=1,
        file_name="test1.stl",
        preset="Ortho Solid - Flat, No Supports",
        confidence="high",
        status="Ready",
    )
    duplicate = ClassificationRow(
        row_id=1,
        file_name="test1.stl",
        preset="Ortho Solid - Flat, No Supports",
        confidence="high",
        status="Ready",
    )
    result = batch_cases_by_preset([row, duplicate])
    assert len(result) == 1
    assert result["Ortho Solid - Flat, No Supports"] == [row]
