"""Phase 1: Task 7 - Status Polling Service Tests (TDD)

Tests for backend polling of Formlabs API and frontend polling of backend.
"""

from __future__ import annotations

from dataclasses import replace
import sys
from pathlib import Path
from datetime import timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient


class _StubSettings:
    def __init__(self, tmp_path: Path):
        from app.config import build_settings

        self._settings = replace(
            build_settings(data_dir=tmp_path, database_path=tmp_path / "andent_web.db"),
            formlabs_api_token="test-token",
        )

    def __getattr__(self, name: str):
        return getattr(self._settings, name)


class _FakeFormlabsClient:
    instances: list["_FakeFormlabsClient"] = []

    def __init__(self, api_token: str, base_url: str = "https://api.formlabs.com/v1"):
        self.api_token = api_token
        self.base_url = base_url
        self.jobs_calls = 0
        self.screenshot_calls = 0
        self.jobs_payload = []
        self.screenshot_payload = b"fake-screenshot-data"
        _FakeFormlabsClient.instances.append(self)

    def list_print_jobs(self):
        self.jobs_calls += 1
        return self.jobs_payload

    def get_job_screenshot(self, job_id: str):
        self.screenshot_calls += 1
        return self.screenshot_payload

    def close(self):
        return None


@pytest.fixture(autouse=True)
def reset_print_queue_cache():
    import app.services.print_queue_service as service

    service._job_cache = None
    service._cache_timestamp = None
    if hasattr(service, "_screenshot_cache"):
        service._screenshot_cache.clear()
    yield
    service._job_cache = None
    service._cache_timestamp = None
    if hasattr(service, "_screenshot_cache"):
        service._screenshot_cache.clear()


@pytest.fixture
def settings(tmp_path: Path):
    return _StubSettings(tmp_path)


@pytest.fixture
def app_client(settings):
    from app.main import create_app

    app = create_app(settings=settings)
    return TestClient(app)


def _create_job(settings, *, job_name: str = "260421-001", print_job_id: str = "job-123", status: str = "Queued"):
    from app.database import create_print_job, init_db
    from app.schemas import PrintJob

    init_db(settings)
    return create_print_job(
        settings,
        PrintJob(
            job_name=job_name,
            print_job_id=print_job_id,
            preset="Ortho Solid - Flat, No Supports",
            status=status,
        ),
    )


def test_backend_polls_formlabs_api_and_updates_db(app_client, settings, monkeypatch):
    from app.database import get_print_job_by_id
    import app.services.print_queue_service as service

    created = _create_job(settings)

    fake_client = _FakeFormlabsClient(api_token="test-token")
    fake_client.jobs_payload = [
        {
            "id": "job-123",
            "status": "Printing",
            "printer": "Form 4BL",
            "resin": "Precision Model Resin",
            "layer_height_microns": 100,
        }
    ]
    monkeypatch.setattr(service, "FormlabsWebClient", lambda api_token, base_url: fake_client)

    response = app_client.get("/api/print-queue/jobs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 1
    assert payload["jobs"][0]["status"] == "Printing"
    assert fake_client.jobs_calls == 1

    updated = get_print_job_by_id(settings, created.id)
    assert updated is not None
    assert updated.status == "Printing"


def test_backend_cache_ttl_blocks_duplicate_formlabs_calls(app_client, settings, monkeypatch):
    import app.services.print_queue_service as service

    _create_job(settings)

    fake_client = _FakeFormlabsClient(api_token="test-token")
    fake_client.jobs_payload = [
        {"id": "job-123", "status": "Queued"},
    ]
    monkeypatch.setattr(service, "FormlabsWebClient", lambda api_token, base_url: fake_client)

    first = app_client.get("/api/print-queue/jobs")
    second = app_client.get("/api/print-queue/jobs")

    assert first.status_code == 200
    assert second.status_code == 200
    assert fake_client.jobs_calls == 1

    service._cache_timestamp = service._cache_timestamp - timedelta(seconds=6)

    third = app_client.get("/api/print-queue/jobs")
    assert third.status_code == 200
    assert fake_client.jobs_calls == 2


def test_screenshots_fetched_and_cached(app_client, settings, monkeypatch):
    from app.database import connect
    import app.services.print_queue_service as service

    created = _create_job(settings)

    fake_client = _FakeFormlabsClient(api_token="test-token")
    monkeypatch.setattr(service, "FormlabsWebClient", lambda api_token, base_url: fake_client)

    response = app_client.get(f"/api/print-queue/jobs/{created.id}/screenshot")
    assert response.status_code == 200
    assert response.content == b"fake-screenshot-data"
    assert fake_client.screenshot_calls == 1

    screenshot_dir = settings.data_dir / "screenshots"
    assert (screenshot_dir / f"job_{created.id}.png").exists()

    second = app_client.get(f"/api/print-queue/jobs/{created.id}/screenshot")
    assert second.status_code == 200
    assert second.content == b"fake-screenshot-data"
    assert fake_client.screenshot_calls == 1

    with connect(settings) as connection:
        row = connection.execute(
            "SELECT screenshot_url FROM print_jobs WHERE id = ?",
            (created.id,),
        ).fetchone()

    assert row is not None
    assert row["screenshot_url"] == str(screenshot_dir / f"job_{created.id}.png")


def test_frontend_polls_backend_every_five_seconds():
    app_js = Path(__file__).parent.parent / "app" / "static" / "app.js"
    source = app_js.read_text(encoding="utf-8")

    assert "PRINT_QUEUE_POLL_INTERVAL = 5000" in source
    assert 'fetch("/api/print-queue/jobs")' in source
