from __future__ import annotations

import logging

from core.batch_optimizer import get_stl_volume_ml

from ..config import Settings
from ..database import get_stored_file_path, get_upload_row_by_id, update_upload_row_volume


def enrich_upload_row_volumes(settings: Settings, row_ids: list[int]) -> int:
    updated_count = 0
    for row_id in row_ids:
        row = get_upload_row_by_id(settings, row_id)
        if row is None or row.volume_ml is not None:
            continue

        stored_path = get_stored_file_path(settings, row_id)
        if stored_path is None or not stored_path.exists():
            continue

        try:
            volume_ml = get_stl_volume_ml(str(stored_path))
        except Exception as exc:
            logging.warning("Volume enrichment failed for row %s: %s", row_id, exc)
            continue

        if volume_ml is None:
            continue

        if update_upload_row_volume(settings, row_id, volume_ml) is not None:
            updated_count += 1

    return updated_count
