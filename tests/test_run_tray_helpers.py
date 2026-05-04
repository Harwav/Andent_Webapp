"""Windows EXE tray launcher helper tests (TDD)."""

from __future__ import annotations

import logging
from pathlib import Path

from app.logging_config import appdata_log_dir, configure_logging
from run_tray import _initial_url, _select_lan_ip


def test_appdata_log_dir_is_created(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    result = appdata_log_dir()
    assert result == tmp_path / "Andent Web" / "logs"
    assert result.is_dir()


def test_configure_logging_creates_log_file(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    log_path = configure_logging(level=logging.DEBUG)
    logging.info("smoke")
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert log_path.exists()
    assert "smoke" in log_path.read_text(encoding="utf-8")


def test_initial_url_targets_setup_on_first_run():
    assert _initial_url(8090, first_run=True) == "http://localhost:8090/setup"


def test_initial_url_targets_app_after_setup():
    assert _initial_url(8090, first_run=False) == "http://localhost:8090/"


def test_select_lan_ip_prefers_rfc1918_address():
    assert _select_lan_ip(["127.0.0.1", "169.254.1.2", "192.168.1.24"]) == "192.168.1.24"


def test_select_lan_ip_falls_back_to_loopback():
    assert _select_lan_ip(["127.0.0.1"]) == "127.0.0.1"
