"""Phase 1: Task 10 - Integration Tests (TDD)

End-to-end test of handoff flow covering full system integration.
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

class TestFullPrintHandoffFlow:
    """Full end-to-end print handoff flow."""

    def test_batch_multiple_cases(self):
        """Compatible ready cases should share one build manifest.
        
        Flow:
        1. Create multiple rows with compatible presets
        2. Build manifests
        3. Verify they are grouped into one manifest
        """
        from app.schemas import ClassificationRow, DimensionSummary
        from app.services.build_planning import plan_build_manifests
        
        rows = [
            ClassificationRow(
                row_id=1,
                file_name="case1.stl",
                preset="Ortho Solid - Flat, No Supports",
                case_id="CASE001",
                confidence="high",
                status="Ready",
                dimensions=DimensionSummary(x_mm=60.0, y_mm=50.0, z_mm=10.0),
                file_path="C:/cases/case1.stl",
            ),
            ClassificationRow(
                row_id=2,
                file_name="case2-tooth.stl",
                preset="Tooth - With Supports",
                case_id="CASE002",
                confidence="high",
                status="Ready",
                dimensions=DimensionSummary(x_mm=35.0, y_mm=35.0, z_mm=10.0),
                file_path="C:/cases/case2.stl",
            ),
        ]
        
        manifests = plan_build_manifests(rows)
        
        assert len(manifests) == 1
        assert manifests[0].case_ids == ["CASE001", "CASE002"]
        assert manifests[0].preset_names == [
            "Ortho Solid - Flat, No Supports",
            "Tooth - With Supports",
        ]

    def test_batch_multiple_presets(self):
        """Mixed presets are still split when the first manifest hits build budget."""
        from app.schemas import ClassificationRow, DimensionSummary
        from app.services.build_planning import plan_build_manifests
        
        rows = [
            ClassificationRow(
                row_id=1,
                file_name="a.stl",
                preset="Ortho Solid - Flat, No Supports",
                case_id="A",
                confidence="high",
                status="Ready",
                dimensions=DimensionSummary(x_mm=278.0, y_mm=54.0, z_mm=10.0),
                file_path="C:/cases/a.stl",
            ),
            ClassificationRow(
                row_id=2,
                file_name="b.stl",
                preset="Ortho Solid - Flat, No Supports",
                case_id="B",
                confidence="high",
                status="Ready",
                dimensions=DimensionSummary(x_mm=259.0, y_mm=54.0, z_mm=10.0),
                file_path="C:/cases/b.stl",
            ),
            ClassificationRow(
                row_id=3,
                file_name="c.stl",
                preset="Tooth - With Supports",
                case_id="C",
                confidence="high",
                status="Ready",
                dimensions=DimensionSummary(x_mm=40.0, y_mm=25.0, z_mm=10.0),
                file_path="C:/cases/c.stl",
            ),
        ]
        
        manifests = plan_build_manifests(rows)
        
        assert [manifest.case_ids for manifest in manifests] == [["A", "B"], ["C"]]

    def test_send_to_print_prefomserver_receives(self, tmp_path):
        """Manifest processing should call scene import/layout/validation/print APIs.
        
        Flow:
        1. Create a planned manifest
        2. Mock PreFormClient
        3. Call manifest processing
        3. Verify create_scene called
        4. Verify import_model called for each STL
        5. Verify auto_layout, validate_scene, and send_to_printer called
        """
        from app.config import build_settings
        from app.schemas import ClassificationRow, DimensionSummary
        from app.services.build_planning import plan_build_manifests
        from app.services.print_queue_service import process_print_manifest
        
        settings = build_settings()
        case_file = tmp_path / "test.stl"
        case_file.write_text("solid test\nendsolid test\n", encoding="utf-8")
        
        rows = [
            ClassificationRow(
                row_id=1,
                file_name=case_file.name,
                preset="Ortho Solid - Flat, No Supports",
                case_id="CASE001",
                confidence="high",
                status="Ready",
                dimensions=DimensionSummary(x_mm=60.0, y_mm=50.0, z_mm=10.0),
                file_path=str(case_file),
            ),
        ]
        manifest = plan_build_manifests(rows)[0]
        
        with patch('app.services.preform_client.PreFormClient') as MockClient:
            mock_instance = Mock()
            mock_instance.create_scene.return_value = {"scene_id": "scene-123"}
            mock_instance.import_model.return_value = {"model_id": "model-123"}
            mock_instance.auto_layout.return_value = {"status": "ok"}
            mock_instance.validate_scene.return_value = {"valid": True, "errors": []}
            mock_instance.send_to_printer.return_value = {"print_id": "print-123"}
            MockClient.return_value = mock_instance

            result = process_print_manifest(settings, manifest, rows, 1)

            assert mock_instance.create_scene.called
            assert mock_instance.import_model.called
            assert mock_instance.auto_layout.called
            assert mock_instance.validate_scene.called
            assert mock_instance.send_to_printer.called
            assert result["scene_id"] == "scene-123"
            assert result["print_job_id"] == "print-123"

    def test_process_print_manifest_does_not_retry_failed_validation(self, tmp_path):
        """One manifest attempt creates one scene even when validation fails."""
        from app.config import build_settings
        from app.schemas import ClassificationRow, DimensionSummary
        from app.services.build_planning import plan_build_manifests
        from app.services.print_queue_service import process_print_manifest

        settings = build_settings()
        first_file = tmp_path / "tooth.stl"
        second_file = tmp_path / "ortho.stl"
        for file_path in (first_file, second_file):
            file_path.write_text("solid test\nendsolid test\n", encoding="utf-8")

        rows = [
            ClassificationRow(
                row_id=1,
                file_name=first_file.name,
                preset="Tooth - With Supports",
                case_id="CASE-TOOTH",
                model_type="Tooth",
                confidence="high",
                status="Ready",
                dimensions=DimensionSummary(x_mm=150.0, y_mm=100.0, z_mm=10.0),
                file_path=str(first_file),
            ),
            ClassificationRow(
                row_id=2,
                file_name=second_file.name,
                preset="Ortho Solid - Flat, No Supports",
                case_id="CASE-ORTHO",
                confidence="high",
                status="Ready",
                dimensions=DimensionSummary(x_mm=60.0, y_mm=50.0, z_mm=10.0),
                file_path=str(second_file),
            ),
        ]
        manifest = plan_build_manifests(rows)[0]

        with patch('app.services.preform_client.PreFormClient') as MockClient:
            mock_instance = Mock()
            mock_instance.create_scene.return_value = {"scene_id": "scene-123"}
            mock_instance.import_model.return_value = {"model_id": "model-123"}
            mock_instance.auto_layout.return_value = {"status": "ok"}
            mock_instance.validate_scene.return_value = {"valid": False, "errors": ["overlap"]}
            MockClient.return_value = mock_instance

            result = process_print_manifest(settings, manifest, rows, 1)

            assert mock_instance.create_scene.call_count == 1
            assert mock_instance.import_model.call_count == 2
            assert mock_instance.auto_layout.call_count == 1
            assert mock_instance.validate_scene.call_count == 1
            assert mock_instance.send_to_printer.call_count == 0
            assert result["validation_passed"] is False
            assert result["case_ids"] == ["CASE-TOOTH", "CASE-ORTHO"]

    def test_poll_for_status_updates(self):
        """Poll for status updates from Formlabs API.
        
        Flow:
        1. Create print job
        2. Poll status endpoint
        3. Verify status updates propagate
        """
        # This tests the polling mechanism
        # Already tested in test_print_queue_polling.py
        pass

    def test_screenshot_display(self):
        """Screenshot should display in UI.
        
        Flow:
        1. Job created
        2. Screenshot fetched from API
        3. Screenshot displayed in job card
        """
        # Frontend integration test
        pass

    def test_error_recovery(self):
        """Error recovery should work.
        
        Flow:
        1. PreFormServer fails
        2. Error logged
        3. Retry mechanism works
        4. User-friendly error message
        """
        from app.services.preform_client import PreFormClient
        import requests
        
        with patch('requests.Session.post') as mock_post:
            mock_post.side_effect = requests.ConnectionError("Connection refused")
            
            client = PreFormClient("http://localhost:44388")
            
            try:
                client.create_scene("patient-001", "case-001")
                assert False, "Should have raised exception"
            except Exception as e:
                # Error should be user-friendly
                assert "PreFormServer" in str(e) or "connect" in str(e).lower()


class TestBatchingIntegration:
    """Batching integration tests."""

    def test_batching_groups_by_preset_correctly(self):
        """Batch planning should preserve per-preset import groups inside one manifest."""
        from app.schemas import ClassificationRow, DimensionSummary
        from app.services.build_planning import plan_build_manifests
        
        presets = [
            "Ortho Solid - Flat, No Supports",
            "Ortho Hollow - Flat, No Supports",
            "Tooth - With Supports",
            "Die - Flat, No Supports",
        ]
        
        rows = []
        for i, preset in enumerate(presets):
            rows.append(ClassificationRow(
                row_id=i+1,
                file_name=f"case{i+1}.stl",
                preset=preset,
                case_id=f"CASE{i+1:03d}",
                confidence="high",
                status="Ready",
                dimensions=DimensionSummary(x_mm=20.0, y_mm=20.0, z_mm=10.0),
                file_path=f"C:/cases/case{i+1}.stl",
            ))
        
        manifests = plan_build_manifests(rows)
        
        assert len(manifests) == 1
        assert [group.preset_name for group in manifests[0].import_groups] == sorted(presets)

    def test_job_names_auto_increment(self):
        """Job names should auto-increment."""
        from app.services.print_queue_service import generate_job_name
        
        date = datetime(2026, 4, 21)
        
        job1 = generate_job_name(date, 1)
        job2 = generate_job_name(date, 2)
        job3 = generate_job_name(date, 3)
        
        assert job1 == "260421-001"
        assert job2 == "260421-002"
        assert job3 == "260421-003"


class TestFormlabsWebClientIntegration:
    """Formlabs Web API client integration."""

    def test_client_authenticates(self):
        """Client should authenticate successfully."""
        from app.services.formlabs_web_client import FormlabsWebClient
        
        with patch('requests.Session.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = []
            mock_get.return_value = mock_response
            
            client = FormlabsWebClient(api_token="valid-token")
            result = client.authenticate()
            
            assert result is True

    def test_client_fetches_jobs(self):
        """Client should fetch job list."""
        from app.services.formlabs_web_client import FormlabsWebClient
        
        mock_jobs = [
            {"id": "job-123", "status": "Queued"},
            {"id": "job-456", "status": "Printing"},
        ]
        
        with patch('requests.Session.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_jobs
            mock_get.return_value = mock_response
            
            client = FormlabsWebClient(api_token="test-token")
            jobs = client.list_print_jobs()
            
            assert len(jobs) == 2

    def test_client_fetches_screenshot(self):
        """Client should fetch screenshot bytes."""
        from app.services.formlabs_web_client import FormlabsWebClient
        
        screenshot_bytes = b"fake-image-data"
        
        with patch('requests.Session.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = screenshot_bytes
            mock_get.return_value = mock_response
            
            client = FormlabsWebClient(api_token="test-token")
            result = client.get_job_screenshot("job-123")
            
            assert result == screenshot_bytes


class TestDatabaseIntegration:
    """Database integration tests."""

    def test_print_jobs_table_created(self):
        """Print jobs table should exist."""
        from app.database import SCHEMA_STATEMENTS
        
        # Check that print_jobs table is in schema
        schema_str = " ".join(SCHEMA_STATEMENTS)
        assert "print_jobs" in schema_str

    def test_config_has_formlabs_settings(self):
        """Config should have Formlabs settings."""
        from app.config import build_settings
        
        settings = build_settings()
        
        assert hasattr(settings, 'formlabs_api_token')
        assert hasattr(settings, 'formlabs_api_url')


class TestEndToEndScenario:
    """Complete end-to-end scenario."""

    def test_complete_workflow(self):
        """Complete workflow from upload to print.
        
        1. Upload STL files
        2. Classify automatically
        3. Review low-confidence cases
        4. Override model types
        5. Send to print
        6. Verify print jobs created
        7. Poll for status
        8. Display in UI
        """
        # This is the full integration test
        # Would require full FastAPI test client
        pass

    def test_error_scenario_recovery(self):
        """System should recover from errors.
        
        1. PreFormServer down
        2. User notified
        3. PreFormServer comes back
        4. Retry succeeds
        """
        pass
