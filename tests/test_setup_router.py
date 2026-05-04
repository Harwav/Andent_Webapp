"""Windows EXE setup wizard router tests (TDD)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import state as runtime_state
from app.config import build_settings
from app.database import init_db, save_preform_setup_state
from app.main import create_app


def _build(tmp_path: Path):
    settings = build_settings(
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "andent_web.db",
    )
    init_db(settings)
    return settings


@pytest.fixture()
def client(tmp_path):
    runtime_state.LAN_IP = "127.0.0.1"
    runtime_state.WIZARD_COMPLETED = False
    runtime_state.LAN_BIND_ALLOWED = False
    settings = _build(tmp_path)
    app = create_app(settings)
    app.state.lan_ip = "192.168.1.100"
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client, settings
    runtime_state.LAN_IP = "127.0.0.1"
    runtime_state.WIZARD_COMPLETED = False
    runtime_state.LAN_BIND_ALLOWED = False


def test_lan_ip_endpoint_returns_json(client):
    test_client, _ = client
    resp = test_client.get("/api/setup/lan-ip")
    assert resp.status_code == 200
    data = resp.json()
    assert data["lan_ip"] == "192.168.1.100"
    assert data["port"] == 8090


def test_setup_page_redirects_when_ready(client):
    test_client, settings = client
    save_preform_setup_state(settings, readiness="ready")
    runtime_state.WIZARD_COMPLETED = True
    resp = test_client.get("/setup")
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/"


def test_setup_page_serves_html_when_not_installed(client):
    test_client, _ = client
    resp = test_client.get("/setup")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert b"setup" in resp.content.lower()


def test_complete_marks_wizard_done_and_records_lan_consent(client):
    test_client, _ = client
    assert runtime_state.WIZARD_COMPLETED is False
    resp = test_client.post("/api/setup/complete", json={"allow_lan": True})
    assert resp.status_code == 200
    assert resp.json()["lan_allowed"] is True
    assert runtime_state.WIZARD_COMPLETED is True
    assert runtime_state.LAN_BIND_ALLOWED is True


def test_complete_can_keep_app_local_only(client):
    test_client, _ = client
    resp = test_client.post("/api/setup/complete", json={"allow_lan": False})
    assert resp.status_code == 200
    assert resp.json()["lan_allowed"] is False
    assert runtime_state.LAN_BIND_ALLOWED is False


def test_setup_html_posts_preform_zip_to_existing_route():
    html = Path("app/static/setup.html").read_text(encoding="utf-8")
    assert 'fetch("/api/preform-setup/install-from-zip"' in html
    assert "/api/preform/setup/install-from-zip" not in html
