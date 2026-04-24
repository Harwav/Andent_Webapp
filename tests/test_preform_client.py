"""Tests for PreFormClient - PreFormServer API client."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
import tempfile

# Add app to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.preform_client import PreFormClient


class TestPreFormClient:
    """Test suite for PreFormClient."""

    def test_init_default_url(self):
        """Test client initializes with default URL."""
        client = PreFormClient()
        assert client.base_url == "http://localhost:44388"

    def test_init_custom_url(self):
        """Test client initializes with custom URL."""
        custom_url = "http://custom-host:12345"
        client = PreFormClient(base_url=custom_url)
        assert client.base_url == custom_url

    def test_create_scene_success(self):
        """Test creating a scene with the current Local API scene-settings payload."""
        # Create a mock session
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "scene-123", "layer_count": 0}
        mock_session.post.return_value = mock_response
        
        client = PreFormClient()
        client.session = mock_session
        
        result = client.create_scene(patient_id="P001", case_name="Test Case")
        
        assert result == {"id": "scene-123", "scene_id": "scene-123", "layer_count": 0}
        mock_session.post.assert_called_once_with(
            "http://localhost:44388/scene/",
            json={
                "layer_thickness_mm": 0.1,
                "machine_type": "FRML-4-0",
                "material_code": "FLPMBE01",
                "print_setting": "DEFAULT",
            },
            timeout=30
        )

    def test_create_scene_accepts_manifest_scene_settings(self):
        """Scene creation uses manifest compatibility settings at the API boundary."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "scene-123"}
        mock_session.post.return_value = mock_response

        client = PreFormClient()
        client.session = mock_session

        result = client.create_scene(
            patient_id="P001",
            case_name="Test Case",
            scene_settings={
                "layer_thickness_mm": 0.1,
                "machine_type": "FORM-4-0",
                "material_code": "FLDLCL02",
                "print_setting": "DEFAULT",
            },
        )

        assert result["scene_id"] == "scene-123"
        mock_session.post.assert_called_once_with(
            "http://localhost:44388/scene/",
            json={
                "layer_thickness_mm": 0.1,
                "machine_type": "FORM-4-0",
                "material_code": "FLDLCL02",
                "print_setting": "DEFAULT",
            },
            timeout=30,
        )

    def test_create_scene_failure(self):
        """Test creating a scene with failure response."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_session.post.return_value = mock_response
        
        client = PreFormClient()
        client.session = mock_session
        
        with pytest.raises(Exception) as exc_info:
            client.create_scene(patient_id="P001", case_name="Test Case")
        
        assert "500" in str(exc_info.value)

    def test_import_model_success(self):
        """Test importing an STL model through the current JSON path contract."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "imported", "model_id": "model-456"}
        mock_session.post.return_value = mock_response
        
        # Create a temporary STL file for testing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.stl', delete=False) as f:
            f.write("solid test\nendsolid test\n")
            temp_path = f.name
        
        try:
            client = PreFormClient()
            client.session = mock_session
            
            result = client.import_model(scene_id="scene-123", stl_path=temp_path)
            
            assert result == {"status": "imported", "model_id": "model-456"}
            mock_session.post.assert_called_once_with(
                "http://localhost:44388/scene/scene-123/import-model",
                json={"file": temp_path},
                timeout=60,
            )
        finally:
            os.unlink(temp_path)

    def test_import_model_sends_preset_hint_when_provided(self):
        """Test importing an STL model with an explicit preset hint."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "imported", "model_id": "model-456"}
        mock_session.post.return_value = mock_response

        with tempfile.NamedTemporaryFile(mode='w', suffix='.stl', delete=False) as f:
            f.write("solid test\nendsolid test\n")
            temp_path = f.name

        try:
            client = PreFormClient()
            client.session = mock_session

            client.import_model(scene_id="scene-123", stl_path=temp_path, preset="tooth_v1")

            assert mock_session.post.call_args.kwargs["json"] == {
                "file": temp_path,
                "preset": "tooth_v1",
            }
        finally:
            os.unlink(temp_path)

    def test_auto_layout_posts_scene_id_payload(self):
        """Test auto-layout posts the scene endpoint and overlap flag."""
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
                json={"allow_overlapping_supports": False, "model_spacing_mm": 1},
                timeout=30,
            )

    def test_auto_layout_rejects_public_overlap_flag(self):
        """Test auto-layout does not expose overlap settings in the public API."""
        with patch("requests.Session.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_post.return_value = mock_response

            client = PreFormClient("http://localhost:44388")

            with pytest.raises(TypeError):
                client.auto_layout("scene-123", allow_overlapping_supports=True)

    def test_auto_layout_raises_on_non_200_response(self):
        """Test auto-layout raises with status and response text on failure."""
        with patch("requests.Session.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "layout failed"
            mock_post.return_value = mock_response

            client = PreFormClient("http://localhost:44388")

            with pytest.raises(Exception) as exc_info:
                client.auto_layout("scene-123")

            assert "500" in str(exc_info.value)
            assert "layout failed" in str(exc_info.value)

    def test_validate_scene_returns_clean_boolean_and_errors(self):
        """Test scene validation returns the API validation payload."""
        with patch("requests.Session.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"valid": False, "errors": ["overlap"]}
            mock_get.return_value = mock_response

            client = PreFormClient("http://localhost:44388")
            result = client.validate_scene("scene-123")

            assert result == {"valid": False, "errors": ["overlap"]}
            mock_get.assert_called_once_with(
                "http://localhost:44388/scene/scene-123/print-validation",
                timeout=30,
            )

    def test_validate_scene_translates_print_validation_payload(self):
        """Test print-validation results are normalized into valid/errors."""
        with patch("requests.Session.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "per_model_results": {
                    "{model-1}": {
                        "cups": 0,
                        "has_seamline": False,
                        "undersupported": False,
                        "unsupported_minima": 0,
                    }
                }
            }
            mock_get.return_value = mock_response

            client = PreFormClient("http://localhost:44388")
            result = client.validate_scene("scene-123")

            assert result == {"valid": True, "errors": []}

    def test_validate_scene_raises_on_non_200_response(self):
        """Test validate_scene raises with status and response text on failure."""
        with patch("requests.Session.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 422
            mock_response.text = "overlap detected"
            mock_get.return_value = mock_response

            client = PreFormClient("http://localhost:44388")

            with pytest.raises(Exception) as exc_info:
                client.validate_scene("scene-123")

            assert "422" in str(exc_info.value)
            assert "overlap detected" in str(exc_info.value)

    def test_send_to_printer_success(self):
        """Test sending print job to printer successfully."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"job_id": "{print-789}"}
        mock_session.post.return_value = mock_response
        
        client = PreFormClient()
        client.session = mock_session
        
        result = client.send_to_printer(scene_id="scene-123", device_id="Form 4", job_name="260421-001")
        
        assert result == {"job_id": "{print-789}", "print_id": "{print-789}"}
        mock_session.post.assert_called_once_with(
            "http://localhost:44388/scene/scene-123/print/",
            json={"job_name": "260421-001", "printer": "Form 4"},
            timeout=30
        )

    def test_list_devices_success(self):
        """Test listing available printers successfully."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"device_id": "printer-01", "name": "Form 3B", "status": "ready"},
            {"device_id": "printer-02", "name": "Form 3L", "status": "busy"}
        ]
        mock_session.get.return_value = mock_response
        
        client = PreFormClient()
        client.session = mock_session
        
        result = client.list_devices()
        
        assert len(result) == 2
        assert result[0]["device_id"] == "printer-01"
        mock_session.get.assert_called_once_with("http://localhost:44388/devices/")

    def test_list_devices_empty(self):
        """Test listing devices when none available."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_session.get.return_value = mock_response
        
        client = PreFormClient()
        client.session = mock_session
        
        result = client.list_devices()
        
        assert result == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
