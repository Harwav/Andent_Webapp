"""Release-gate preset normalization tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import build_settings
from app.database import (
    bulk_update_upload_rows,
    init_db,
    persist_upload_session,
    update_upload_row,
)


def _build_settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    settings = build_settings(data_dir=data_dir, database_path=data_dir / "andent_web.db")
    init_db(settings)
    return settings


def _seed_row(settings, file_name: str, *, model_type: str, preset: str):
    stored_path = settings.data_dir / file_name
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    stored_path.write_text("solid fixture\nendsolid fixture\n", encoding="utf-8")
    rows = persist_upload_session(
        settings,
        "session-1",
        [
            {
                "file_name": file_name,
                "stored_path": str(stored_path),
                "content_hash": f"hash-{file_name}",
                "thumbnail_svg": None,
                "case_id": "CASE555",
                "model_type": model_type,
                "preset": preset,
                "confidence": "high",
                "status": "Ready",
                "dimension_x_mm": None,
                "dimension_y_mm": None,
                "dimension_z_mm": None,
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
    return rows[0].row_id


def test_update_upload_row_maps_model_label_to_real_preset(tmp_path):
    settings = _build_settings(tmp_path)
    row_id = _seed_row(
        settings,
        "20260409_CASE555_Tooth_46.stl",
        model_type="Tooth",
        preset="Tooth - With Supports",
    )

    updated = update_upload_row(settings, row_id, "Ortho - Solid", "Ortho - Solid")

    assert updated is not None
    assert updated.model_type == "Ortho - Solid"
    assert updated.preset == "Ortho Solid - Flat, No Supports"
    assert updated.status == "Ready"


def test_bulk_update_upload_rows_maps_model_label_to_real_preset(tmp_path):
    settings = _build_settings(tmp_path)
    row_id = _seed_row(
        settings,
        "20260409_CASE555_Tooth_46.stl",
        model_type="Tooth",
        preset="Tooth - With Supports",
    )

    rows = bulk_update_upload_rows(settings, [row_id], "Splint", "Splint")

    assert rows[0].model_type == "Splint"
    assert rows[0].preset == "Splint - Flat, No Supports"
    assert rows[0].status == "Ready"
