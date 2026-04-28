"""Phase 2: 3D preview modal backend tests."""

from __future__ import annotations

from pathlib import Path


APP_JS = Path("app/static/app.js")


def test_thumbnail_snapshot_storage_prefix_constant():
    """Verify the thumbnail snapshot localStorage prefix constant is defined."""
    app_js = APP_JS.read_text(encoding="utf-8")

    assert 'THUMBNAIL_SNAPSHOT_STORAGE_PREFIX = "andent:thumbnail-snapshot:"' in app_js


def test_preview_state_structure():
    """Verify the preview state object has required fields."""
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "preview: {" in app_js
    assert "renderer: null" in app_js
    assert "frameId: null" in app_js
    assert "cleanup: null" in app_js


def test_thumbnail_snapshots_cache_structure():
    """Verify the thumbnail snapshots cache has the expected structure."""
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "thumbnailSnapshots:" in app_js
    assert "cache: new Map()" in app_js
    assert "pending: new Set()" in app_js
    assert "queue: []" in app_js
    assert "active: 0" in app_js
    assert "maxActive: 2" in app_js


def test_preview_modal_dom_elements():
    """Verify all preview modal DOM elements are defined in elements object."""
    app_js = APP_JS.read_text(encoding="utf-8")

    assert 'previewModal: document.getElementById("preview-modal")' in app_js
    assert 'previewViewer: document.getElementById("preview-viewer")' in app_js
    assert 'closePreview: document.getElementById("close-preview")' in app_js
    assert 'previewTitle: document.getElementById("preview-title")' in app_js
    assert 'previewCaption: document.getElementById("preview-caption")' in app_js


def test_ensure_preview_dependencies_function():
    """Verify the ensurePreviewDependencies function loads Three.js from esm.sh."""
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "async function ensurePreviewDependencies()" in app_js
    assert "esm.sh" in app_js
    assert "STLLoader" in app_js
    assert "THREE" in app_js


def test_preview_modal_show_hide():
    """Verify preview modal can be shown and hidden."""
    app_js = APP_JS.read_text(encoding="utf-8")

    assert 'previewModal.classList.remove("hidden")' in app_js
    assert 'previewModal.classList.add("hidden")' in app_js
    assert 'previewModal.setAttribute("aria-hidden", "false")' in app_js
    assert 'previewModal.setAttribute("aria-hidden", "true")' in app_js


def test_preview_modal_click_outside_close():
    """Verify clicking outside the preview content closes the modal."""
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "elements.previewModal.addEventListener" in app_js
    assert "previewModal.classList.add" in app_js


def test_stl_file_endpoint_exists():
    """Verify the STL file download endpoint is defined in uploads router."""
    uploads_py = Path("app/routers/uploads.py").read_text(encoding="utf-8")

    assert '@router.get("/rows/{row_id}/file"' in uploads_py
    assert "async def get_row_file" in uploads_py
    assert "media_type=\"model/stl\"" in uploads_py


def test_thumbnail_snapshots_local_storage_operations():
    """Verify localStorage get/set operations use the snapshot prefix."""
    app_js = APP_JS.read_text(encoding="utf-8")

    assert "localStorage.getItem" in app_js
    assert "localStorage.setItem" in app_js
    assert "THUMBNAIL_SNAPSHOT_STORAGE_PREFIX" in app_js
