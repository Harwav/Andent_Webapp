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
        """Test creating a scene successfully."""
        # Create a mock session
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"scene_id": "scene-123", "status": "created"}
        mock_session.post.return_value = mock_response
        
        client = PreFormClient()
        client.session = mock_session
        
        result = client.create_scene(patient_id="P001", case_name="Test Case")
        
        assert result == {"scene_id": "scene-123", "status": "created"}
        mock_session.post.assert_called_once_with(
            "http://localhost:44388/scene/",
            json={"patient_id": "P001", "case_name": "Test Case"},
            timeout=30
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
        """Test importing an STL model successfully."""
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
            mock_session.post.assert_called_once()
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

            assert mock_session.post.call_args.kwargs["data"] == {"preset": "tooth_v1"}
        finally:
            os.unlink(temp_path)

    def test_send_to_printer_success(self):
        """Test sending print job to printer successfully."""
        mock_session = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"print_id": "print-789", "status": "queued"}
        mock_session.post.return_value = mock_response
        
        client = PreFormClient()
        client.session = mock_session
        
        result = client.send_to_printer(scene_id="scene-123", device_id="printer-01")
        
        assert result == {"print_id": "print-789", "status": "queued"}
        mock_session.post.assert_called_once_with(
            "http://localhost:44388/print/",
            json={"scene_id": "scene-123", "device_id": "printer-01"},
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
