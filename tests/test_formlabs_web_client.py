"""Phase 1: Task 4 - FormlabsWebClient Tests (TDD)

Tests for Formlabs Web API client.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


def test_client_initialization():
    """Client should initialize with API token and base URL."""
    from app.services.formlabs_web_client import FormlabsWebClient
    
    client = FormlabsWebClient(
        api_token="test-token-123",
        base_url="https://api.formlabs.com/v1"
    )
    assert client.api_token == "test-token-123"
    assert client.base_url == "https://api.formlabs.com/v1"


def test_client_default_base_url():
    """Client should use default base URL if not provided."""
    from app.services.formlabs_web_client import FormlabsWebClient
    
    client = FormlabsWebClient(api_token="test-token")
    assert client.base_url == "https://api.formlabs.com/v1"


def test_authenticate_success():
    """Authenticate should return True on successful auth."""
    from app.services.formlabs_web_client import FormlabsWebClient
    
    with patch('requests.Session.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        client = FormlabsWebClient(api_token="valid-token")
        result = client.authenticate()
        
        assert result is True


def test_authenticate_failure():
    """Authenticate should return False on auth failure."""
    from app.services.formlabs_web_client import FormlabsWebClient
    
    with patch('requests.Session.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response
        
        client = FormlabsWebClient(api_token="invalid-token")
        result = client.authenticate()
        
        assert result is False


def test_list_print_jobs():
    """Should fetch and return list of print jobs."""
    from app.services.formlabs_web_client import FormlabsWebClient
    
    mock_jobs = [
        {
            "id": "job-123",
            "status": "Queued",
            "printer": "Form 4BL",
            "resin": "Precision Model Resin",
            "layer_height_microns": 100,
            "created_at": "2026-04-21T10:00:00Z",
        },
        {
            "id": "job-456",
            "status": "Printing",
            "printer": "Form 4BL",
            "resin": "Precision Model Resin",
            "layer_height_microns": 100,
            "created_at": "2026-04-21T11:00:00Z",
        },
    ]
    
    with patch('requests.Session.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_jobs
        mock_get.return_value = mock_response
        
        client = FormlabsWebClient(api_token="test-token")
        result = client.list_print_jobs()
        
        assert len(result) == 2
        assert result[0]["id"] == "job-123"
        assert result[0]["status"] == "Queued"


def test_get_job_status():
    """Should fetch status for specific job."""
    from app.services.formlabs_web_client import FormlabsWebClient
    
    mock_job = {
        "id": "job-123",
        "status": "Printing",
        "printer": "Form 4BL",
        "resin": "Precision Model Resin",
        "layer_height_microns": 100,
        "progress_percent": 45,
        "estimated_completion": "2026-04-21T12:00:00Z",
    }
    
    with patch('requests.Session.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_job
        mock_get.return_value = mock_response
        
        client = FormlabsWebClient(api_token="test-token")
        result = client.get_job_status("job-123")
        
        assert result["id"] == "job-123"
        assert result["status"] == "Printing"
        assert result["progress_percent"] == 45


def test_get_job_screenshot():
    """Should fetch screenshot bytes for job."""
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


def test_auth_header_included():
    """All requests should include Authorization header."""
    from app.services.formlabs_web_client import FormlabsWebClient
    
    with patch('requests.Session.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response
        
        client = FormlabsWebClient(api_token="test-token")
        client.list_print_jobs()
        
        # Headers are set on session in __init__, not per-request
        assert client.session.headers.get("Authorization") == "Token test-token"


def test_error_handling_network():
    """Should handle network errors gracefully."""
    from app.services.formlabs_web_client import FormlabsWebClient
    import requests
    
    with patch('requests.Session.get') as mock_get:
        mock_get.side_effect = requests.RequestException("Connection refused")
        
        client = FormlabsWebClient(api_token="test-token")
        
        with pytest.raises(Exception):
            client.list_print_jobs()


def test_error_handling_401():
    """Should handle 401 auth errors."""
    from app.services.formlabs_web_client import FormlabsWebClient
    
    with patch('requests.Session.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response
        
        client = FormlabsWebClient(api_token="invalid-token")
        result = client.authenticate()
        
        assert result is False
