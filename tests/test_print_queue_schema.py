"""Phase 1: Task 5 - Print Queue Database Schema Tests (TDD)

Tests for print_jobs table and related schema changes.
"""

import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


def test_print_job_schema_creation():
    """PrintJob schema should validate correctly."""
    from app.schemas import PrintJob
    from datetime import datetime
    
    job = PrintJob(
        id=1,
        job_name="260421-001",
        scene_id="scene-123",
        print_job_id="print-123",
        status="Queued",
        preset="Ortho Solid - Flat, No Supports",
        case_ids=["CASE001", "CASE002"],
        form_file_path="D:/cases/260421-001.form",
        printer_type="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
    )
    
    assert job.job_name == "260421-001"
    assert job.scene_id == "scene-123"
    assert job.status == "Queued"
    assert job.form_file_path == "D:/cases/260421-001.form"
    assert len(job.case_ids) == 2


def test_print_job_case_ids_json():
    """case_ids should be stored as JSON."""
    from app.schemas import PrintJob
    
    job = PrintJob(
        id=1,
        job_name="260421-001",
        preset="Ortho Solid - Flat, No Supports",
        case_ids=["CASE001", "CASE002"],
    )
    
    # Should serialize to JSON
    case_ids_json = json.dumps(job.case_ids)
    assert case_ids_json == '["CASE001", "CASE002"]'


def test_print_job_optional_fields():
    """Optional fields should be nullable."""
    from app.schemas import PrintJob
    
    job = PrintJob(
        id=1,
        job_name="260421-001",
        preset="Ortho Solid - Flat, No Supports",
        scene_id=None,
        print_job_id=None,
        form_file_path=None,
        status="Queued",
        case_ids=[],
    )
    
    assert job.scene_id is None
    assert job.print_job_id is None
    assert job.form_file_path is None


def test_config_has_formlabs_api_token():
    """Settings should include FORMLABS_API_TOKEN."""
    from app.config import build_settings
    import os
    
    # Set env var
    os.environ["FORMLABS_API_TOKEN"] = "test-token-123"
    
    settings = build_settings()
    
    # Should have formlabs_api_token attribute
    assert hasattr(settings, 'formlabs_api_token')
    assert settings.formlabs_api_token == "test-token-123"
    
    # Clean up
    del os.environ["FORMLABS_API_TOKEN"]


def test_config_default_formlabs_api_url():
    """Settings should have default Formlabs API URL."""
    from app.config import build_settings
    
    settings = build_settings()
    
    assert hasattr(settings, 'formlabs_api_url')
    assert settings.formlabs_api_url == "https://api.formlabs.com/v1"
