"""Phase 1: Upload classification persistence tests (TDD)."""

from __future__ import annotations

import io
import pathlib
import struct
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.config import build_settings
from app.database import connect, init_db
from app.main import create_app


def _build_settings(tmp_path):
    data_dir = tmp_path / "data"
    settings = build_settings(data_dir=data_dir, database_path=data_dir / "andent_web.db")
    init_db(settings)
    return settings


def _minimal_stl_bytes() -> bytes:
    header = b"\x00" * 80
    count = struct.pack("<I", 1)
    normal = struct.pack("<fff", 0, 0, 1)
    v1 = struct.pack("<fff", 0, 0, 0)
    v2 = struct.pack("<fff", 1, 0, 0)
    v3 = struct.pack("<fff", 0, 1, 0)
    attr = struct.pack("<H", 0)
    return header + count + normal + v1 + v2 + v3 + attr


def test_classify_upload_persists_single_row(tmp_path):
    settings = _build_settings(tmp_path)
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/uploads/classify",
        files=[("files", ("P001_die.stl", io.BytesIO(_minimal_stl_bytes()), "model/stl"))],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["file_count"] == 1
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["file_name"] == "P001_die.stl"

    with connect(settings) as connection:
        stored = connection.execute(
            "SELECT file_name, stored_path, content_hash FROM upload_rows"
        ).fetchall()

    assert len(stored) == 1
    assert stored[0]["file_name"] == "P001_die.stl"
    assert pathlib.Path(stored[0]["stored_path"]).exists()
    assert stored[0]["content_hash"]


def test_classify_upload_marks_existing_hash_as_duplicate(tmp_path):
    settings = _build_settings(tmp_path)
    client = TestClient(create_app(settings))
    stl_bytes = _minimal_stl_bytes()

    first = client.post(
        "/api/uploads/classify",
        files=[("files", ("P001_die.stl", io.BytesIO(stl_bytes), "model/stl"))],
    )
    assert first.status_code == 200

    second = client.post(
        "/api/uploads/classify",
        files=[("files", ("P001_die_copy.stl", io.BytesIO(stl_bytes), "model/stl"))],
    )

    assert second.status_code == 200
    duplicate_row = second.json()["rows"][0]
    assert duplicate_row["status"] == "Duplicate"

