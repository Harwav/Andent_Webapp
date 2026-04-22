"""Phase 1: Upload classification persistence tests (TDD)."""

from __future__ import annotations

import io
import pathlib
import struct
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.config import build_settings
from app.database import connect, get_upload_row_by_id, init_db, persist_upload_session
from app.main import create_app
from app.schemas import ClassificationRow
from app.services.classification import classify_saved_upload, serialize_row_for_storage


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


def test_public_upload_and_queue_responses_do_not_expose_file_path(tmp_path):
    settings = _build_settings(tmp_path)
    client = TestClient(create_app(settings))

    classify_response = client.post(
        "/api/uploads/classify",
        files=[("files", ("P001_die.stl", io.BytesIO(_minimal_stl_bytes()), "model/stl"))],
    )

    assert classify_response.status_code == 200
    classify_payload = classify_response.json()
    assert "file_path" not in classify_payload["rows"][0]

    queue_response = client.get("/api/uploads/queue")

    assert queue_response.status_code == 200
    queue_payload = queue_response.json()
    public_rows = queue_payload["active_rows"] + queue_payload["processed_rows"]
    assert public_rows
    assert all("file_path" not in row for row in public_rows)


def test_antag_upload_classifies_with_case_id_and_ortho_solid_preset(tmp_path, monkeypatch):
    from app.services import classification

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Antag filename classification should not need thickness sampling")
    def fail_volume_if_called(*args, **kwargs):
        raise AssertionError("Antag filename classification should not need exact volume")

    monkeypatch.setattr(classification, "measure_mesh_thickness_stats", fail_if_called)
    monkeypatch.setattr(classification, "get_stl_volume_ml", fail_volume_if_called)
    stl_path = tmp_path / "20260408_8425357__Kaleen_Shium_Antag.stl"
    stl_path.write_bytes(_minimal_stl_bytes())

    row = classify_saved_upload(stl_path, stl_path.name)

    assert row.case_id == "8425357"
    assert row.model_type == "Antagonist"
    assert row.preset == "Ortho Solid - Flat, No Supports"
    assert row.status == "Ready"


def test_unsectioned_model_classifies_solid_without_thickness_sampling(tmp_path, monkeypatch):
    from app.services import classification

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Named unsectioned models should not need thickness sampling")
    def fail_volume_if_called(*args, **kwargs):
        raise AssertionError("Named unsectioned models should not need exact volume")

    monkeypatch.setattr(classification, "measure_mesh_thickness_stats", fail_if_called)
    monkeypatch.setattr(classification, "get_stl_volume_ml", fail_volume_if_called)
    stl_path = tmp_path / "20260408_8425357__Kaleen_Shium_UnsectionedModel_LowerJaw.stl"
    stl_path.write_bytes(_minimal_stl_bytes())

    row = classify_saved_upload(stl_path, stl_path.name)

    assert row.case_id == "8425357"
    assert row.model_type == "Ortho - Solid"
    assert row.preset == "Ortho Solid - Flat, No Supports"
    assert row.status == "Ready"


def test_serialize_row_for_storage_defers_thumbnail_generation(tmp_path, monkeypatch):
    from app.services import classification

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Thumbnail generation should not block upload persistence")

    monkeypatch.setattr(classification, "generate_thumbnail_svg", fail_if_called)
    stl_path = tmp_path / "20260408_8425357__Kaleen_Shium_Antag.stl"
    stl_path.write_bytes(_minimal_stl_bytes())
    row = ClassificationRow(
        file_name=stl_path.name,
        case_id="8425357",
        model_type="Antagonist",
        preset="Ortho Solid - Flat, No Supports",
        confidence="high",
        status="Ready",
    )

    payload = serialize_row_for_storage(row, stl_path, "hash-1")

    assert payload["thumbnail_svg"] is None


def test_enrich_upload_row_volumes_updates_missing_volume(tmp_path, monkeypatch):
    from app.services import volume_enrichment

    settings = _build_settings(tmp_path)
    stl_path = tmp_path / "20260408_8425357__Kaleen_Shium_Antag.stl"
    stl_path.write_bytes(_minimal_stl_bytes())
    rows = persist_upload_session(
        settings,
        "session-volume",
        [
            {
                "file_name": stl_path.name,
                "stored_path": str(stl_path),
                "content_hash": "hash-volume",
                "thumbnail_svg": None,
                "case_id": "8425357",
                "model_type": "Antagonist",
                "preset": "Ortho Solid - Flat, No Supports",
                "confidence": "high",
                "status": "Ready",
                "dimension_x_mm": 1.0,
                "dimension_y_mm": 1.0,
                "dimension_z_mm": 0.0,
                "volume_ml": None,
                "structure": None,
                "structure_confidence": None,
                "structure_reason": None,
                "structure_metrics_json": None,
                "structure_locked": False,
                "review_required": False,
                "review_reason": None,
                "printer": None,
                "person": None,
            }
        ],
    )
    row_id = rows[0].row_id
    monkeypatch.setattr(volume_enrichment, "get_stl_volume_ml", lambda path: 1.234)

    updated_count = volume_enrichment.enrich_upload_row_volumes(settings, [row_id])

    updated = get_upload_row_by_id(settings, row_id)
    assert updated_count == 1
    assert updated.volume_ml == 1.234


def test_classify_upload_defers_volume_to_background_queue_update(tmp_path, monkeypatch):
    from app.services import classification, volume_enrichment

    settings = _build_settings(tmp_path)
    client = TestClient(create_app(settings))

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Initial fast-path classification should not compute exact volume")

    monkeypatch.setattr(classification, "get_stl_volume_ml", fail_if_called)
    monkeypatch.setattr(volume_enrichment, "get_stl_volume_ml", lambda path: 2.5)

    response = client.post(
        "/api/uploads/classify",
        files=[
            (
                "files",
                (
                    "20260408_8425357__Kaleen_Shium_Antag.stl",
                    io.BytesIO(_minimal_stl_bytes()),
                    "model/stl",
                ),
            )
        ],
    )

    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["model_type"] == "Antagonist"
    assert row["volume_ml"] is None

    queue_response = client.get("/api/uploads/queue")
    assert queue_response.status_code == 200
    queued_row = queue_response.json()["active_rows"][0]
    assert queued_row["volume_ml"] == 2.5


def test_classification_row_accepts_antagonist_model_type():
    row = ClassificationRow(
        file_name="20260408_8425357__Kaleen_Shium_Antag.stl",
        case_id="8425357",
        model_type="Antagonist",
        preset="Ortho Solid - Flat, No Supports",
        confidence="high",
        status="Ready",
    )

    assert row.model_type == "Antagonist"

