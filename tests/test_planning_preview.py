import pathlib
import io
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest
from app.config import build_settings
from app.database import init_db, persist_upload_session, get_upload_row_by_id


@pytest.fixture
def tmp_settings(tmp_path):
    s = build_settings(data_dir=tmp_path / "data", database_path=tmp_path / "data" / "test.db")
    init_db(s)
    return s


def _minimal_row(file_name="test.stl"):
    return {
        "file_name": file_name,
        "stored_path": "/tmp/test.stl",
        "content_hash": "abc123",
        "thumbnail_svg": None,
        "case_id": "P001",
        "model_type": "Die",
        "preset": "Die",
        "confidence": "high",
        "status": "Ready",
        "dimension_x_mm": 10.0,
        "dimension_y_mm": 10.0,
        "dimension_z_mm": 5.0,
        "volume_ml": 0.5,
        "review_required": False,
        "review_reason": None,
    }


def test_get_upload_row_by_id_returns_row(tmp_settings):
    rows = persist_upload_session(tmp_settings, "sess1", [_minimal_row()])
    row = get_upload_row_by_id(tmp_settings, rows[0].row_id)
    assert row is not None
    assert row.file_name == "test.stl"


def test_get_upload_row_by_id_missing_returns_none(tmp_settings):
    result = get_upload_row_by_id(tmp_settings, 9999)
    assert result is None


# --- planning_preview service unit tests ---

from app.services.planning_preview import build_row_preview, build_batch_preview
from app.schemas import ClassificationRow


def _make_row(row_id=1, case_id="P001", model_type="Die", preset="Die", status="Ready"):
    return ClassificationRow(
        row_id=row_id,
        file_name=f"case_{case_id}.stl",
        case_id=case_id,
        model_type=model_type,
        preset=preset,
        confidence="high",
        status=status,
    )


def test_build_row_preview_ready_row():
    row = _make_row()
    preview = build_row_preview(row)
    assert preview.row_id == 1
    assert preview.preview_available is True
    assert preview.cannot_fit is False


def test_build_row_preview_no_model_type():
    row = _make_row(model_type=None, preset=None)
    preview = build_row_preview(row)
    assert preview.preview_available is False


def test_build_batch_preview_groups_by_case():
    rows = [
        _make_row(row_id=1, case_id="P001"),
        _make_row(row_id=2, case_id="P001"),
        _make_row(row_id=3, case_id="P002"),
    ]
    result = build_batch_preview(rows)
    assert result.group_count == 2
    assert result.cannot_fit_count == 0
    assert len(result.rows) == 3


# --- API endpoint tests ---

from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client(tmp_settings):
    app = create_app(settings=tmp_settings)
    return TestClient(app)


def _minimal_stl_bytes() -> bytes:
    import struct
    header = b"\x00" * 80
    count = struct.pack("<I", 1)
    normal = struct.pack("<fff", 0, 0, 1)
    v1 = struct.pack("<fff", 0, 0, 0)
    v2 = struct.pack("<fff", 1, 0, 0)
    v3 = struct.pack("<fff", 0, 1, 0)
    attr = struct.pack("<H", 0)
    return header + count + normal + v1 + v2 + v3 + attr


def _upload_stl(client, content: bytes | None = None, filename="P001_die.stl"):
    return client.post(
        "/api/uploads/classify",
        files=[("files", (filename, io.BytesIO(content or _minimal_stl_bytes()), "model/stl"))],
    )


def test_single_row_plan_preview(client):
    upload_resp = _upload_stl(client)
    assert upload_resp.status_code == 200
    row_id = upload_resp.json()["rows"][0]["row_id"]
    resp = client.get(f"/api/uploads/rows/{row_id}/plan-preview")
    assert resp.status_code == 200
    data = resp.json()
    assert "row_id" in data
    assert "preview_available" in data


def test_single_row_plan_preview_not_found(client):
    resp = client.get("/api/uploads/rows/9999/plan-preview")
    assert resp.status_code == 404


def test_batch_plan_preview(client):
    r1 = _upload_stl(client, filename="P001_die.stl")
    r2 = _upload_stl(client, filename="P002_tooth.stl")
    id1 = r1.json()["rows"][0]["row_id"]
    id2 = r2.json()["rows"][0]["row_id"]
    resp = client.post("/api/uploads/rows/batch-plan-preview", json={"row_ids": [id1, id2]})
    assert resp.status_code == 200
    data = resp.json()
    assert "rows" in data
    assert "group_count" in data
    assert len(data["rows"]) == 2
