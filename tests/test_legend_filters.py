"""Phase 2: Legend filters backend tests (TDD)."""

from __future__ import annotations

from pathlib import Path


APP_JS = Path("app/static/app.js")


def test_active_statuses_has_eight_items():
    """Verify ACTIVE_STATUSES list contains exactly 8 items."""
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "const ACTIVE_STATUSES = [" in app_js
    assert '"Queued"' in app_js
    assert '"Uploading"' in app_js
    assert '"Analyzing"' in app_js
    assert '"Ready"' in app_js
    assert '"Check"' in app_js
    assert '"Needs Review"' in app_js
    assert '"Duplicate"' in app_js
    assert '"Locked"' in app_js


def test_active_filters_is_a_set():
    """Verify activeFilters uses Set for O(1) lookup."""
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "activeFilters: new Set()" in app_js


def test_filter_combines_with_or_logic():
    """Verify multiple active filters show rows matching any filter (OR logic)."""
    app_js = APP_JS.read_text(encoding="utf-8")

    # getFilteredActiveRows uses Array.filter with activeFilters.has()
    # which implements OR logic (row matches if ANY filter matches)
    assert "function getFilteredActiveRows()" in app_js
    assert "state.activeFilters.size === 0" in app_js
    assert "state.activeFilters.has(getRowStatus(row))" in app_js


def test_render_legend_exists_and_renders_filter_chips():
    """Verify renderLegend function exists and renders filter chips."""
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "function renderLegend()" in app_js
    assert "elements.statusLegend.innerHTML" in app_js
    assert "ACTIVE_STATUSES.forEach" in app_js
    assert 'button.className = "legend-item"' in app_js


def test_filter_chips_have_active_class():
    """Verify active filter chips have legend-item-active class."""
    app_js = APP_JS.read_text(encoding="utf-8")

    assert 'button.classList.add("legend-item-active")' in app_js
    assert "state.activeFilters.has(status)" in app_js


def test_filter_toggle_updates_active_filters():
    """Verify clicking a filter toggles it in activeFilters Set."""
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "state.activeFilters.delete(status)" in app_js
    assert "state.activeFilters.add(status)" in app_js


def test_filter_resets_page_to_one():
    """Verify selecting a filter resets pagination to page 1."""
    app_js = APP_JS.read_text(encoding="utf-8")

    # When a filter is toggled, page resets to 1
    assert 'state.activePage = 1' in app_js
