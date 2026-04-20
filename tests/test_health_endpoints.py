"""Phase 4: Health Endpoint Tests (TDD)"""
import pytest
from fastapi.testclient import TestClient
from andent_web.app.main import app


client = TestClient(app)


class TestHealthEndpoints:
    """Test health check endpoints for production readiness."""

    def test_health_endpoint_returns_200(self):
        """Test /health returns 200 OK."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"

    def test_health_live_endpoint(self):
        """Test /health/live liveness probe."""
        response = client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["alive"] == True

    def test_health_ready_endpoint(self):
        """Test /health/ready readiness probe."""
        response = client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert "ready" in data

    def test_health_contains_timestamp(self):
        """Test health response includes timestamp."""
        response = client.get("/health")
        data = response.json()
        assert "timestamp" in data