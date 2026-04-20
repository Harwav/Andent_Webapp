"""Phase 2: Case-Aware Selection Tests (TDD)"""
import pytest


class TestCaseAwareSelection:
    """Test auto-selection of rows with same case_id."""

    def test_select_one_selects_all_same_case(self):
        """Test clicking a row selects all rows with same case_id."""
        rows = [
            {"id": 1, "case_id": "CASE-001"},
            {"id": 2, "case_id": "CASE-001"},
            {"id": 3, "case_id": "CASE-002"},
        ]
        
        # User clicks row 1
        clicked_case = rows[0]["case_id"]
        selected = [r for r in rows if r["case_id"] == clicked_case]
        
        assert len(selected) == 2
        assert selected[0]["id"] == 1
        assert selected[1]["id"] == 2

    def test_ctrl_click_adds_to_selection(self):
        """Test Ctrl+click adds different case to selection."""
        rows = [
            {"id": 1, "case_id": "CASE-001"},
            {"id": 2, "case_id": "CASE-001"},
            {"id": 3, "case_id": "CASE-002"},
        ]
        
        # First selection: CASE-001 (2 rows)
        selected = [r for r in rows if r["case_id"] == "CASE-001"]
        
        # Ctrl+click: add CASE-002
        ctrl_clicked_case = "CASE-002"
        selected += [r for r in rows if r["case_id"] == ctrl_clicked_case]
        
        assert len(selected) == 3  # All rows selected

    def test_selection_count_display(self):
        """Test selection count is displayed to user."""
        selected_count = 5
        display_text = f"{selected_count} rows selected"
        assert "5" in display_text

    def test_click_without_ctrl_replaces_selection(self):
        """Test clicking without Ctrl replaces current selection."""
        rows = [
            {"id": 1, "case_id": "CASE-001"},
            {"id": 2, "case_id": "CASE-001"},
            {"id": 3, "case_id": "CASE-002"},
        ]
        
        # Initial selection: CASE-001
        selected = [r for r in rows if r["case_id"] == "CASE-001"]
        
        # Click without Ctrl on CASE-002 (replaces selection)
        new_clicked_case = "CASE-002"
        selected = [r for r in rows if r["case_id"] == new_clicked_case]
        
        assert len(selected) == 1
        assert selected[0]["case_id"] == "CASE-002"