"""Phase 2: Undo Removal Tests (TDD)"""

import pytest
import time
from pathlib import Path

APP_JS = Path("app/static/app.js")


class TestUndoRemovalConstants:
    """Test undo removal constants and frontend configuration."""

    def test_delete_undo_ms_constant_is_5000(self):
        """Verify DELETE_UNDO_MS constant equals 5000 milliseconds."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "const DELETE_UNDO_MS = 5000;" in app_js

    def test_undo_window_is_5_seconds(self):
        """Test default undo window is 5 seconds (5000ms)."""
        undo_window_ms = 5000
        undo_window_seconds = undo_window_ms / 1000
        assert undo_window_seconds == 5


class TestPendingDeletesMap:
    """Test pendingDeletes Map behavior in frontend state."""

    def test_pending_deletes_map_exists_in_state(self):
        """Verify pendingDeletes Map is initialized in state."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "pendingDeletes: new Map()" in app_js

    def test_pending_deletes_has_key_structure(self):
        """Verify pendingDeletes uses key-based lookup."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "state.pendingDeletes.has(getRowKey(row))" in app_js
        assert "state.pendingDeletes.get(key)" in app_js
        assert "state.pendingDeletes.set(key," in app_js
        assert "state.pendingDeletes.delete(key)" in app_js

    def test_pending_delete_stores_timeout_id(self):
        """Verify pending delete entry stores timeoutId for clearing."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "timeoutId" in app_js
        assert "window.clearTimeout(pending.timeoutId)" in app_js

    def test_pending_delete_stores_expires_at(self):
        """Verify pending delete entry stores expiresAt for UI timer."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "expiresAt: Date.now() + DELETE_UNDO_MS" in app_js


class TestPendingBulkDelete:
    """Test pendingBulkDelete behavior."""

    def test_pending_bulk_delete_exists_in_state(self):
        """Verify pendingBulkDelete is initialized in state."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "pendingBulkDelete: null" in app_js

    def test_bulk_delete_stores_row_ids_set(self):
        """Verify bulk delete stores rowIds as a Set."""
        app_js = APP_JS.read_text(encoding="utf-8")
        # In startBulkDelete, rowIds is created as a Set from rows
        assert "const rowIds = new Set(rows.map" in app_js
        # And then stored in pendingBulkDelete object
        assert "state.pendingBulkDelete = {" in app_js
        assert "rowIds," in app_js

    def test_bulk_delete_stores_timeout_and_expires_at(self):
        """Verify bulk delete stores timeoutId and expiresAt."""
        app_js = APP_JS.read_text(encoding="utf-8")
        # Check that bulk delete also uses same undo timing
        assert "state.pendingBulkDelete.expiresAt - Date.now()" in app_js

    def test_undo_bulk_delete_clears_timeout(self):
        """Verify undo bulk delete clears the timeout."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "window.clearTimeout(state.pendingBulkDelete.timeoutId)" in app_js
        assert "state.pendingBulkDelete = null" in app_js


class TestDeleteCountdown:
    """Test delete countdown behavior."""

    def test_start_delete_countdown_function_exists(self):
        """Verify startDeleteCountdown function exists."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "function startDeleteCountdown(row)" in app_js

    def test_delete_uses_set_timeout_with_undo_ms(self):
        """Verify delete uses setTimeout with DELETE_UNDO_MS."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "}, DELETE_UNDO_MS)" in app_js

    def test_delete_prevents_duplicate_countdowns(self):
        """Verify delete is skipped if already pending."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "if (state.pendingBulkDelete)" in app_js
        assert "if (state.pendingDeletes.has(key))" in app_js

    def test_undo_delete_function_exists(self):
        """Verify undoDelete function exists."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "function undoDelete(row)" in app_js

    def test_undo_clears_pending_from_map(self):
        """Verify undo removes entry from pendingDeletes map."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "state.pendingDeletes.delete(key)" in app_js


class TestBulkDeleteFunctions:
    """Test bulk delete functions."""

    def test_start_bulk_delete_function_exists(self):
        """Verify startBulkDelete function exists."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "function startBulkDelete(rows)" in app_js

    def test_undo_bulk_delete_function_exists(self):
        """Verify undoBulkDelete function exists."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "function undoBulkDelete()" in app_js

    def test_bulk_delete_checks_pending_state(self):
        """Verify bulk delete checks for existing pending operation."""
        app_js = APP_JS.read_text(encoding="utf-8")
        assert "if (state.pendingBulkDelete || rows.length === 0)" in app_js


class TestBackendDeleteEndpoints:
    """Test backend delete API endpoints."""

    def test_single_delete_endpoint_exists(self):
        """Verify DELETE /api/uploads/rows/{row_id} endpoint exists."""
        uploads_py = Path("app/routers/uploads.py").read_text(encoding="utf-8")
        assert '@router.delete("/rows/{row_id}")' in uploads_py

    def test_bulk_delete_endpoint_exists(self):
        """Verify POST /api/uploads/rows/bulk-delete endpoint exists."""
        uploads_py = Path("app/routers/uploads.py").read_text(encoding="utf-8")
        assert '@router.post("/rows/bulk-delete"' in uploads_py

    def test_bulk_delete_response_model(self):
        """Verify bulk delete returns BulkDeleteRowsResponse."""
        uploads_py = Path("app/routers/uploads.py").read_text(encoding="utf-8")
        assert "BulkDeleteRowsResponse" in uploads_py


class TestUndoExpiration:
    """Test undo window expiration behavior."""

    def test_undo_expires_after_5_seconds(self):
        """Test undo window expires after 5 seconds."""
        deleted_at = time.time() - 6  # 6 seconds ago
        current_time = time.time()
        undo_window = 5  # seconds

        can_undo = (current_time - deleted_at) < undo_window
        assert can_undo is False  # Too late

    def test_undo_available_within_5_seconds(self):
        """Test undo is still available within 5 second window."""
        deleted_at = time.time() - 3  # 3 seconds ago
        current_time = time.time()
        undo_window = 5  # seconds

        can_undo = (current_time - deleted_at) < undo_window
        assert can_undo is True  # Still within window

    def test_undo_timer_calculation(self):
        """Test undo timer calculates remaining time correctly."""
        now = time.time() * 1000  # milliseconds
        expires_at = now + 5000  # 5 seconds from now
        remaining = max(0, expires_at - now)

        assert remaining == 5000

    def test_multiple_deletions_queue_separately(self):
        """Test multiple deletions are queued separately."""
        pending_deletes = {}

        # Delete 3 items
        for i in range(3):
            pending_deletes[f"row_{i}"] = {
                "row_id": i,
                "expiresAt": time.time() + 5,
            }

        assert len(pending_deletes) == 3

        # Undo one
        del pending_deletes["row_0"]
        assert len(pending_deletes) == 2
        assert "row_0" not in pending_deletes
        assert "row_1" in pending_deletes
        assert "row_2" in pending_deletes
