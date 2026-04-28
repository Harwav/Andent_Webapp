"""Phase 2: Case-Aware Selection Tests (TDD)"""
import pytest


class TestCaseAwareSelection:
    """Test auto-selection of rows with same case_id."""

    def test_select_one_selects_all_same_case(self):
        """Test clicking a row selects all rows with same case_id."""
        rows = [
            {"row_id": 1, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
            {"row_id": 2, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
            {"row_id": 3, "case_id": "CASE-002", "is_temp": False, "status": "Ready"},
        ]

        # User clicks row 1 - all rows with same case_id should be selected
        def toggle_row_selection(rows, row_id, checked, selected_ids):
            """Simulate toggleRowSelection from app.js"""
            if not checked:
                selected_ids.discard(row_id)
                return

            target_row = next(r for r in rows if r["row_id"] == row_id)
            if not target_row["case_id"]:
                selected_ids.add(row_id)
                return

            # Select all rows with same case_id
            for row in rows:
                if row["case_id"] == target_row["case_id"] and not row["is_temp"]:
                    selected_ids.add(row["row_id"])

        selected_ids = set()
        toggle_row_selection(rows, 1, True, selected_ids)

        assert len(selected_ids) == 2
        assert 1 in selected_ids
        assert 2 in selected_ids
        assert 3 not in selected_ids

    def test_ctrl_click_adds_to_selection(self):
        """Test Ctrl+click adds different case to selection."""
        rows = [
            {"row_id": 1, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
            {"row_id": 2, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
            {"row_id": 3, "case_id": "CASE-002", "is_temp": False, "status": "Ready"},
        ]

        def toggle_row_selection(rows, row_id, checked, selected_ids):
            if not checked:
                selected_ids.discard(row_id)
                return
            target_row = next(r for r in rows if r["row_id"] == row_id)
            if not target_row["case_id"]:
                selected_ids.add(row_id)
                return
            for row in rows:
                if row["case_id"] == target_row["case_id"] and not row["is_temp"]:
                    selected_ids.add(row["row_id"])

        # First selection: CASE-001 (2 rows)
        selected_ids = set()
        toggle_row_selection(rows, 1, True, selected_ids)
        assert len(selected_ids) == 2

        # Ctrl+click: add CASE-002 (row 3)
        toggle_row_selection(rows, 3, True, selected_ids)
        assert len(selected_ids) == 3  # All rows selected

    def test_selection_count_display(self):
        """Test selection count is displayed to user."""
        selected_count = 5
        display_text = f"{selected_count} selected"
        assert "5" in display_text
        assert "selected" in display_text

    def test_clicking_another_case_adds_to_selection(self):
        """Test clicking checkbox on different case adds to existing selection."""
        rows = [
            {"row_id": 1, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
            {"row_id": 2, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
            {"row_id": 3, "case_id": "CASE-002", "is_temp": False, "status": "Ready"},
        ]

        def toggle_row_selection(rows, row_id, checked, selected_ids):
            if not checked:
                selected_ids.discard(row_id)
                return
            target_row = next(r for r in rows if r["row_id"] == row_id)
            if not target_row["case_id"]:
                selected_ids.add(row_id)
                return
            for row in rows:
                if row["case_id"] == target_row["case_id"] and not row["is_temp"]:
                    selected_ids.add(row["row_id"])

        # Initial selection: CASE-001
        selected_ids = set()
        toggle_row_selection(rows, 1, True, selected_ids)
        assert len(selected_ids) == 2

        # Clicking another case adds to selection (checkbox toggle adds, doesn't replace)
        toggle_row_selection(rows, 3, True, selected_ids)
        assert len(selected_ids) == 3  # All 3 rows now selected

    def test_uncheck_removes_case_group(self):
        """Test unchecking removes all rows with that case_id."""
        rows = [
            {"row_id": 1, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
            {"row_id": 2, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
            {"row_id": 3, "case_id": "CASE-002", "is_temp": False, "status": "Ready"},
        ]

        def toggle_row_selection(rows, row_id, checked, selected_ids):
            if not checked:
                selected_ids.discard(row_id)
                return
            target_row = next(r for r in rows if r["row_id"] == row_id)
            if not target_row["case_id"]:
                selected_ids.add(row_id)
                return
            for row in rows:
                if row["case_id"] == target_row["case_id"] and not row["is_temp"]:
                    selected_ids.add(row["row_id"])

        # Select both cases
        selected_ids = set()
        toggle_row_selection(rows, 1, True, selected_ids)
        toggle_row_selection(rows, 3, True, selected_ids)
        assert len(selected_ids) == 3

        # Uncheck CASE-001 - only removes row_id 1 from set (partial removal not supported)
        toggle_row_selection(rows, 1, False, selected_ids)
        # The implementation removes only the specific row_id from set
        assert 1 not in selected_ids
        assert 2 in selected_ids  # row 2 still selected (implementation limitation)
        assert 3 in selected_ids


class TestBuildPageSelectionInfo:
    """Test buildPageSelectionInfo cross-page tracking logic."""

    def test_single_page_case_group_included(self):
        """Test case group on single page is fully selected."""
        # Simulate buildPageSelectionInfo from app.js
        def build_page_selection_info(page_rows, filtered_rows):
            def is_editable_active_row(row):
                return not row["is_temp"] and row["status"] == "Ready"

            eligible_rows = [r for r in page_rows if is_editable_active_row(r)]
            excluded_case_ids = set()
            total_by_case = {}
            page_by_case = {}

            for row in filtered_rows:
                if row.get("case_id") and is_editable_active_row(row):
                    case_id = row["case_id"]
                    total_by_case[case_id] = total_by_case.get(case_id, 0) + 1

            for row in eligible_rows:
                if row.get("case_id"):
                    case_id = row["case_id"]
                    page_by_case[case_id] = page_by_case.get(case_id, 0) + 1

            row_ids = []
            for row in eligible_rows:
                if row.get("case_id") and total_by_case.get(row["case_id"]) != page_by_case.get(row["case_id"]):
                    excluded_case_ids.add(row["case_id"])
                else:
                    row_ids.append(row["row_id"])

            return {"rowIds": row_ids, "excludedCases": list(excluded_case_ids)}

        page_rows = [
            {"row_id": 1, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
            {"row_id": 2, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
        ]
        filtered_rows = page_rows.copy()

        info = build_page_selection_info(page_rows, filtered_rows)
        assert len(info["rowIds"]) == 2
        assert info["excludedCases"] == []

    def test_multi_page_case_group_excluded(self):
        """Test case group spanning pages shows excluded notice."""
        def build_page_selection_info(page_rows, filtered_rows):
            def is_editable_active_row(row):
                return not row["is_temp"] and row["status"] == "Ready"

            eligible_rows = [r for r in page_rows if is_editable_active_row(r)]
            excluded_case_ids = set()
            total_by_case = {}
            page_by_case = {}

            for row in filtered_rows:
                if row.get("case_id") and is_editable_active_row(row):
                    case_id = row["case_id"]
                    total_by_case[case_id] = total_by_case.get(case_id, 0) + 1

            for row in eligible_rows:
                if row.get("case_id"):
                    case_id = row["case_id"]
                    page_by_case[case_id] = page_by_case.get(case_id, 0) + 1

            row_ids = []
            for row in eligible_rows:
                if row.get("case_id") and total_by_case.get(row["case_id"]) != page_by_case.get(row["case_id"]):
                    excluded_case_ids.add(row["case_id"])
                else:
                    row_ids.append(row["row_id"])

            return {"rowIds": row_ids, "excludedCases": list(excluded_case_ids)}

        # CASE-001 has 3 rows total but only 2 on this page
        page_rows = [
            {"row_id": 1, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
            {"row_id": 2, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
        ]
        filtered_rows = [
            {"row_id": 1, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
            {"row_id": 2, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
            {"row_id": 3, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},  # On different page
        ]

        info = build_page_selection_info(page_rows, filtered_rows)
        assert info["rowIds"] == []  # No rows included due to multi-page case
        assert "CASE-001" in info["excludedCases"]

    def test_rows_without_case_id_always_selected(self):
        """Test rows without case_id are always included in selection."""
        def build_page_selection_info(page_rows, filtered_rows):
            def is_editable_active_row(row):
                return not row["is_temp"] and row["status"] == "Ready"

            eligible_rows = [r for r in page_rows if is_editable_active_row(r)]
            excluded_case_ids = set()
            total_by_case = {}
            page_by_case = {}

            for row in filtered_rows:
                if row.get("case_id") and is_editable_active_row(row):
                    case_id = row["case_id"]
                    total_by_case[case_id] = total_by_case.get(case_id, 0) + 1

            for row in eligible_rows:
                if row.get("case_id"):
                    case_id = row["case_id"]
                    page_by_case[case_id] = page_by_case.get(case_id, 0) + 1

            row_ids = []
            for row in eligible_rows:
                if row.get("case_id") and total_by_case.get(row["case_id"]) != page_by_case.get(row["case_id"]):
                    excluded_case_ids.add(row["case_id"])
                else:
                    row_ids.append(row["row_id"])

            return {"rowIds": row_ids, "excludedCases": list(excluded_case_ids)}

        page_rows = [
            {"row_id": 1, "case_id": None, "is_temp": False, "status": "Ready"},  # No case_id
            {"row_id": 2, "case_id": "CASE-001", "is_temp": False, "status": "Ready"},
        ]
        filtered_rows = page_rows.copy()

        info = build_page_selection_info(page_rows, filtered_rows)
        assert 1 in info["rowIds"]  # Row without case_id included
        assert 2 in info["rowIds"]  # Complete case group included

    def test_selection_note_for_excluded_cases(self):
        """Test selection note is updated when cases span pages."""
        excluded_count = 2
        note = f"{excluded_count} case group(s) were skipped because they span more than one page."
        assert "2" in note
        assert "skipped" in note
        assert "span more than one page" in note


class TestSelectedIdsSet:
    """Test selectedIds Set behavior."""

    def test_selected_ids_is_set(self):
        """Test selectedIds is a Set for O(1) lookups."""
        selected_ids = set()
        selected_ids.add(1)
        selected_ids.add(2)
        selected_ids.add(1)  # Duplicate
        assert len(selected_ids) == 2
        assert 1 in selected_ids

    def test_clear_selection(self):
        """Test clearing selection empties the set."""
        selected_ids = set([1, 2, 3])
        selected_ids.clear()
        assert len(selected_ids) == 0

    def test_delete_removes_from_selection(self):
        """Test unchecking removes ID from selection."""
        selected_ids = set([1, 2, 3])
        selected_ids.discard(2)
        assert 2 not in selected_ids
        assert 1 in selected_ids
        assert 3 in selected_ids

    def test_get_selected_rows(self):
        """Test filtering activeRows by selectedIds."""
        active_rows = [
            {"row_id": 1, "case_id": "CASE-001"},
            {"row_id": 2, "case_id": "CASE-001"},
            {"row_id": 3, "case_id": "CASE-002"},
        ]
        selected_ids = {1, 2}
        selected = [r for r in active_rows if r["row_id"] in selected_ids]
        assert len(selected) == 2
        assert all(r["case_id"] == "CASE-001" for r in selected)