"""Phase 2: Real-time Polling Tests (TDD)"""
import pytest
from unittest.mock import MagicMock, patch
import time
from pathlib import Path


class TestPollingIntervals:
    """Test polling interval configuration values."""

    def test_print_queue_poll_interval_is_5_seconds(self):
        """Verify PRINT_QUEUE_POLL_INTERVAL = 5000 from app.js"""
        app_js = Path(__file__).parent.parent / "app" / "static" / "app.js"
        source = app_js.read_text(encoding="utf-8")

        assert "PRINT_QUEUE_POLL_INTERVAL = 5000" in source

    def test_work_queue_poll_interval_is_10_seconds(self):
        """Verify work queue polls every 10 seconds (window.pollInterval = 10000)"""
        app_js = Path(__file__).parent.parent / "app" / "static" / "app.js"
        source = app_js.read_text(encoding="utf-8")

        # Verify work queue interval is 10 seconds
        assert "window.pollInterval = 10000" in source
        assert "Queue polling - auto-refresh every 10 seconds" in source

    def test_print_queue_uses_print_queue_poll_interval(self):
        """Verify print queue setInterval uses window.printQueuePollInterval"""
        app_js = Path(__file__).parent.parent / "app" / "static" / "app.js"
        source = app_js.read_text(encoding="utf-8")

        # Verify print queue interval is assigned
        assert "window.printQueuePollInterval = PRINT_QUEUE_POLL_INTERVAL" in source
        # Verify print queue uses the interval in setInterval
        assert ", window.printQueuePollInterval);" in source


class TestPollingPauseResume:
    """Test polling pause/resume behavior via window.pollingPaused."""

    def test_polling_paused_flag_exists(self):
        """Verify window.pollingPaused flag is initialized"""
        app_js = Path(__file__).parent.parent / "app" / "static" / "app.js"
        source = app_js.read_text(encoding="utf-8")

        assert "window.pollingPaused = false" in source

    def test_work_queue_polling_respects_paused_flag(self):
        """Verify work queue polling checks pollingPaused before fetching"""
        app_js = Path(__file__).parent.parent / "app" / "static" / "app.js"
        source = app_js.read_text(encoding="utf-8")

        # Extract the work queue polling block
        work_queue_poll_idx = source.find("// Queue polling")
        if work_queue_poll_idx == -1:
            pytest.fail("Work queue polling code not found")

        poll_block = source[work_queue_poll_idx:work_queue_poll_idx + 600]
        assert "window.pollingPaused" in poll_block
        assert "if (window.pollingPaused) return" in poll_block

    def test_print_queue_polling_respects_paused_flag(self):
        """Verify print queue polling checks pollingPaused before fetching"""
        app_js = Path(__file__).parent.parent / "app" / "static" / "app.js"
        source = app_js.read_text(encoding="utf-8")

        # Extract the print queue polling block
        print_queue_poll_idx = source.find("Print queue polling")
        if print_queue_poll_idx == -1:
            pytest.fail("Print queue polling code not found")

        poll_block = source[print_queue_poll_idx:print_queue_poll_idx + 500]
        assert "window.pollingPaused" in poll_block
        assert "if (window.pollingPaused) return" in poll_block


class TestPollingErrorHandling:
    """Test polling error handling behavior."""

    def test_work_queue_poll_has_error_handling(self):
        """Verify work queue polling has try/catch error handling"""
        app_js = Path(__file__).parent.parent / "app" / "static" / "app.js"
        source = app_js.read_text(encoding="utf-8")

        # Extract the work queue polling block
        work_queue_poll_idx = source.find("// Queue polling")
        poll_block = source[work_queue_poll_idx:work_queue_poll_idx + 600]

        # Verify error handling structure
        assert "try {" in poll_block
        assert "catch (error)" in poll_block
        assert 'console.error("Polling error:", error.message)' in poll_block

    def test_print_queue_poll_has_error_handling(self):
        """Verify print queue polling has try/catch error handling"""
        app_js = Path(__file__).parent.parent / "app" / "static" / "app.js"
        source = app_js.read_text(encoding="utf-8")

        # Extract the print queue polling block
        print_queue_poll_idx = source.find("Print queue polling")
        poll_block = source[print_queue_poll_idx:print_queue_poll_idx + 1200]

        # Verify error handling structure
        assert "try {" in poll_block
        assert "catch (error)" in poll_block
        assert 'console.error("Print queue polling error:", error.message)' in poll_block


class TestManualRefresh:
    """Test manual refresh behavior."""

    def test_manual_refresh_defined_in_code(self):
        """Verify manual refresh functions exist"""
        app_js = Path(__file__).parent.parent / "app" / "static" / "app.js"
        source = app_js.read_text(encoding="utf-8")

        # Verify fetchQueue and fetchPrintQueue functions exist
        assert "async function fetchQueue" in source
        assert "async function fetchPrintQueue" in source

    def test_fetch_queue_endpoint_exists(self):
        """Verify queue polling hits the correct API endpoint"""
        app_js = Path(__file__).parent.parent / "app" / "static" / "app.js"
        source = app_js.read_text(encoding="utf-8")

        # Verify endpoints being polled
        assert 'fetch("/api/uploads/queue")' in source
        assert 'fetch("/api/print-queue/jobs")' in source
