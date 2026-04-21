from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import Settings
from .schemas import ClassificationRow, DimensionSummary, PrintJob
from .services.classification import (
    default_preset,
    derive_status,
    generate_thumbnail_svg,
    is_current_thumbnail_svg,
)


SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS upload_sessions (
        session_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        file_count INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS upload_rows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        file_name TEXT NOT NULL,
        stored_path TEXT NOT NULL,
        content_hash TEXT,
        thumbnail_svg TEXT,
        case_id TEXT,
        model_type TEXT,
        preset TEXT,
        confidence TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Ready',
        dimension_x_mm REAL,
        dimension_y_mm REAL,
        dimension_z_mm REAL,
        volume_ml REAL,
        review_required INTEGER NOT NULL DEFAULT 0,
        review_reason TEXT,
        printer TEXT,
        person TEXT,
        current_event_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(session_id) REFERENCES upload_sessions(session_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS upload_row_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        row_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        event_at TEXT NOT NULL,
        metadata_json TEXT,
        FOREIGN KEY(row_id) REFERENCES upload_rows(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS print_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_name TEXT NOT NULL UNIQUE,
        scene_id TEXT,
        print_job_id TEXT,
        status TEXT NOT NULL DEFAULT 'Queued',
        preset TEXT NOT NULL,
        preset_names_json TEXT,
        compatibility_key TEXT,
        case_ids TEXT,
        manifest_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        screenshot_url TEXT,
        printer_type TEXT,
        resin TEXT,
        layer_height_microns INTEGER,
        estimated_completion TIMESTAMP,
        error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS preform_setup_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        readiness TEXT NOT NULL,
        install_path TEXT NOT NULL,
        managed_executable_path TEXT NOT NULL,
        detected_version TEXT,
        last_health_check_at TEXT,
        last_error_code TEXT,
        last_error_message TEXT,
        active_configured_source INTEGER NOT NULL DEFAULT 1,
        process_id INTEGER,
        updated_at TEXT NOT NULL
    )
    """,
)

INDEX_STATEMENTS: tuple[str, ...] = (
    """
    CREATE INDEX IF NOT EXISTS ix_upload_rows_session_id
    ON upload_rows(session_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_upload_rows_status
    ON upload_rows(status)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_upload_rows_content_hash
    ON upload_rows(content_hash)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_print_jobs_status
    ON print_jobs(status)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_print_jobs_created_at
    ON print_jobs(created_at)
    """,
)


def ensure_storage(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)


def connect(settings: Settings) -> sqlite3.Connection:
    ensure_storage(settings)
    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    existing = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in existing:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init_db(settings: Settings) -> None:
    with closing(connect(settings)) as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)

        _ensure_column(connection, "upload_rows", "content_hash", "TEXT")
        _ensure_column(connection, "upload_rows", "thumbnail_svg", "TEXT")
        _ensure_column(connection, "upload_rows", "status", "TEXT NOT NULL DEFAULT 'Ready'")
        _ensure_column(connection, "upload_rows", "volume_ml", "REAL")
        _ensure_column(connection, "upload_rows", "structure", "TEXT")
        _ensure_column(connection, "upload_rows", "structure_confidence", "TEXT")
        _ensure_column(connection, "upload_rows", "structure_reason", "TEXT")
        _ensure_column(connection, "upload_rows", "structure_metrics_json", "TEXT")
        _ensure_column(connection, "upload_rows", "structure_locked", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "upload_rows", "printer", "TEXT")
        _ensure_column(connection, "upload_rows", "person", "TEXT")
        _ensure_column(connection, "upload_rows", "current_event_at", "TEXT")
        _ensure_column(connection, "print_jobs", "preset_names_json", "TEXT")
        _ensure_column(connection, "print_jobs", "manifest_json", "TEXT")
        _ensure_column(connection, "print_jobs", "compatibility_key", "TEXT")
        connection.execute(
            """
            UPDATE upload_rows
            SET confidence = 'low'
            WHERE confidence NOT IN ('high', 'medium', 'low')
            """
        )
        for statement in INDEX_STATEMENTS:
            connection.execute(statement)
        connection.commit()


def _row_to_print_job(row: sqlite3.Row) -> PrintJob:
    case_ids: list[str] = []
    if row["case_ids"]:
        try:
            loaded_case_ids = json.loads(row["case_ids"])
            if isinstance(loaded_case_ids, list):
                case_ids = [str(case_id) for case_id in loaded_case_ids]
        except json.JSONDecodeError:
            case_ids = []

    preset_names: list[str] = []
    if row["preset_names_json"]:
        try:
            loaded_preset_names = json.loads(row["preset_names_json"])
            if isinstance(loaded_preset_names, list):
                preset_names = [str(preset_name) for preset_name in loaded_preset_names]
        except json.JSONDecodeError:
            preset_names = []

    manifest_json: dict[str, object] | None = None
    if row["manifest_json"]:
        try:
            loaded_manifest = json.loads(row["manifest_json"])
            if isinstance(loaded_manifest, dict):
                manifest_json = loaded_manifest
        except json.JSONDecodeError:
            manifest_json = None

    return PrintJob(
        id=row["id"],
        job_name=row["job_name"],
        scene_id=row["scene_id"],
        print_job_id=row["print_job_id"],
        status=row["status"],
        preset=row["preset"],
        preset_names=preset_names,
        compatibility_key=row["compatibility_key"],
        case_ids=case_ids,
        manifest_json=manifest_json,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        screenshot_url=row["screenshot_url"],
        printer_type=row["printer_type"],
        resin=row["resin"],
        layer_height_microns=row["layer_height_microns"],
        estimated_completion=row["estimated_completion"],
        error_message=row["error_message"],
    )


def _fetch_print_job(connection: sqlite3.Connection, *, job_id: int | None = None, job_name: str | None = None) -> PrintJob | None:
    if job_id is None and job_name is None:
        return None

    if job_id is not None:
        row = connection.execute("SELECT * FROM print_jobs WHERE id = ?", (job_id,)).fetchone()
    else:
        row = connection.execute("SELECT * FROM print_jobs WHERE job_name = ?", (job_name,)).fetchone()

    return _row_to_print_job(row) if row else None


def create_print_job(settings: Settings, print_job: PrintJob) -> PrintJob:
    now = _now_iso()
    preset_names_json = json.dumps(print_job.preset_names)
    case_ids_json = json.dumps(print_job.case_ids)
    manifest_json = json.dumps(print_job.manifest_json) if print_job.manifest_json is not None else None

    with closing(connect(settings)) as connection:
        cursor = connection.execute(
            """
            INSERT INTO print_jobs (
                job_name,
                scene_id,
                print_job_id,
                status,
                preset,
                preset_names_json,
                compatibility_key,
                case_ids,
                manifest_json,
                created_at,
                updated_at,
                screenshot_url,
                printer_type,
                resin,
                layer_height_microns,
                estimated_completion,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                print_job.job_name,
                print_job.scene_id,
                print_job.print_job_id,
                print_job.status,
                print_job.preset,
                preset_names_json,
                print_job.compatibility_key,
                case_ids_json,
                manifest_json,
                print_job.created_at or now,
                print_job.updated_at or now,
                print_job.screenshot_url,
                print_job.printer_type,
                print_job.resin,
                print_job.layer_height_microns,
                print_job.estimated_completion,
                print_job.error_message,
            ),
        )
        connection.commit()

        created = _fetch_print_job(connection, job_id=int(cursor.lastrowid))
        if created is None:
            raise RuntimeError("Failed to load created print job.")
        return created


def list_print_jobs(settings: Settings) -> list[PrintJob]:
    with closing(connect(settings)) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM print_jobs
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
        return [_row_to_print_job(row) for row in rows]


def get_print_job_by_id(settings: Settings, job_id: int) -> PrintJob | None:
    with closing(connect(settings)) as connection:
        return _fetch_print_job(connection, job_id=job_id)


def get_print_job_by_name(settings: Settings, job_name: str) -> PrintJob | None:
    with closing(connect(settings)) as connection:
        return _fetch_print_job(connection, job_name=job_name)


def update_print_job(settings: Settings, job_id: int, **changes: object) -> PrintJob | None:
    if not changes:
        return get_print_job_by_id(settings, job_id)

    allowed_fields = {
        "job_name",
        "scene_id",
        "print_job_id",
        "status",
        "preset",
        "preset_names",
        "compatibility_key",
        "case_ids",
        "manifest_json",
        "screenshot_url",
        "printer_type",
        "resin",
        "layer_height_microns",
        "estimated_completion",
        "error_message",
    }

    with closing(connect(settings)) as connection:
        existing = connection.execute("SELECT id FROM print_jobs WHERE id = ?", (job_id,)).fetchone()
        if existing is None:
            return None

        assignments: list[str] = []
        values: list[object] = []
        for field, value in changes.items():
            if field not in allowed_fields:
                continue
            if field == "preset_names":
                field = "preset_names_json"
                value = json.dumps(value if value is not None else [])
            elif field == "case_ids" and value is not None:
                value = json.dumps(value)
            elif field == "manifest_json" and value is not None:
                value = json.dumps(value)
            assignments.append(f"{field} = ?")
            values.append(value)

        if not assignments:
            return _fetch_print_job(connection, job_id=job_id)

        assignments.append("updated_at = ?")
        values.append(_now_iso())
        values.append(job_id)

        connection.execute(
            f"""
            UPDATE print_jobs
            SET {', '.join(assignments)}
            WHERE id = ?
            """,
            tuple(values),
        )
        connection.commit()
        return _fetch_print_job(connection, job_id=job_id)


def _default_preform_setup_state(settings: Settings) -> dict[str, object]:
    return {
        "id": 1,
        "readiness": "not_installed",
        "install_path": str(settings.preform_managed_dir),
        "managed_executable_path": str(settings.preform_managed_executable),
        "detected_version": None,
        "last_health_check_at": None,
        "last_error_code": None,
        "last_error_message": None,
        "active_configured_source": 1,
        "process_id": None,
        "updated_at": _now_iso(),
    }


def load_preform_setup_state(settings: Settings) -> dict[str, object]:
    with closing(connect(settings)) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM preform_setup_state
            WHERE id = 1
            """
        ).fetchone()
        if row is None:
            return _default_preform_setup_state(settings)
        return {
            "id": row["id"],
            "readiness": row["readiness"],
            "install_path": row["install_path"],
            "managed_executable_path": row["managed_executable_path"],
            "detected_version": row["detected_version"],
            "last_health_check_at": row["last_health_check_at"],
            "last_error_code": row["last_error_code"],
            "last_error_message": row["last_error_message"],
            "active_configured_source": row["active_configured_source"],
            "process_id": row["process_id"],
            "updated_at": row["updated_at"],
        }


def save_preform_setup_state(settings: Settings, **changes: object) -> dict[str, object]:
    current = load_preform_setup_state(settings)
    payload = {
        "id": 1,
        "readiness": changes.get("readiness", current["readiness"]),
        "install_path": changes.get("install_path", current["install_path"]),
        "managed_executable_path": changes.get(
            "managed_executable_path",
            current["managed_executable_path"],
        ),
        "detected_version": changes.get("detected_version", current["detected_version"]),
        "last_health_check_at": changes.get(
            "last_health_check_at",
            current["last_health_check_at"],
        ),
        "last_error_code": changes.get("last_error_code", current["last_error_code"]),
        "last_error_message": changes.get(
            "last_error_message",
            current["last_error_message"],
        ),
        "active_configured_source": 1
        if changes.get(
            "active_configured_source",
            bool(current["active_configured_source"]),
        )
        else 0,
        "process_id": changes.get("process_id", current["process_id"]),
        "updated_at": _now_iso(),
    }

    with closing(connect(settings)) as connection:
        connection.execute(
            """
            INSERT INTO preform_setup_state (
                id,
                readiness,
                install_path,
                managed_executable_path,
                detected_version,
                last_health_check_at,
                last_error_code,
                last_error_message,
                active_configured_source,
                process_id,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                readiness = excluded.readiness,
                install_path = excluded.install_path,
                managed_executable_path = excluded.managed_executable_path,
                detected_version = excluded.detected_version,
                last_health_check_at = excluded.last_health_check_at,
                last_error_code = excluded.last_error_code,
                last_error_message = excluded.last_error_message,
                active_configured_source = excluded.active_configured_source,
                process_id = excluded.process_id,
                updated_at = excluded.updated_at
            """,
            (
                payload["id"],
                payload["readiness"],
                payload["install_path"],
                payload["managed_executable_path"],
                payload["detected_version"],
                payload["last_health_check_at"],
                payload["last_error_code"],
                payload["last_error_message"],
                payload["active_configured_source"],
                payload["process_id"],
                payload["updated_at"],
            ),
        )
        connection.commit()

    return payload


def delete_print_job(settings: Settings, job_id: int) -> bool:
    with closing(connect(settings)) as connection:
        cursor = connection.execute("DELETE FROM print_jobs WHERE id = ?", (job_id,))
        connection.commit()
        return cursor.rowcount > 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_event(
    connection: sqlite3.Connection,
    row_id: int,
    event_type: str,
    event_at: str,
    metadata: dict | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO upload_row_events (row_id, event_type, event_at, metadata_json)
        VALUES (?, ?, ?, ?)
        """,
        (row_id, event_type, event_at, json.dumps(metadata or {})),
    )


def _normalize_manual_preset(model_type: str | None, preset: str | None) -> str | None:
    if preset is None:
        return default_preset(model_type) if model_type else None

    normalized_from_model_label = default_preset(preset)
    if normalized_from_model_label is not None:
        return normalized_from_model_label

    return preset


def persist_upload_session(settings: Settings, session_id: str, rows: Iterable[dict]) -> list[ClassificationRow]:
    created_at = _now_iso()
    row_list = list(rows)

    with closing(connect(settings)) as connection:
        connection.execute(
            """
            INSERT INTO upload_sessions (session_id, created_at, file_count)
            VALUES (?, ?, ?)
            """,
            (session_id, created_at, len(row_list)),
        )

        inserted_ids: list[int] = []
        for row in row_list:
            cursor = connection.execute(
                """
                INSERT INTO upload_rows (
                    session_id,
                    file_name,
                    stored_path,
                    content_hash,
                    thumbnail_svg,
                    case_id,
                    model_type,
                    preset,
                    confidence,
                    status,
                    dimension_x_mm,
                    dimension_y_mm,
                    dimension_z_mm,
                    volume_ml,
                    structure,
                    structure_confidence,
                    structure_reason,
                    structure_metrics_json,
                    structure_locked,
                    review_required,
                    review_reason,
                    printer,
                    person,
                    current_event_at,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    row["file_name"],
                    row["stored_path"],
                    row["content_hash"],
                    row.get("thumbnail_svg"),
                    row["case_id"],
                    row["model_type"],
                    row["preset"],
                    row["confidence"],
                    row["status"],
                    row["dimension_x_mm"],
                    row["dimension_y_mm"],
                    row["dimension_z_mm"],
                    row["volume_ml"],
                    row.get("structure"),
                    row.get("structure_confidence"),
                    row.get("structure_reason"),
                    row.get("structure_metrics_json"),
                    1 if row.get("structure_locked") else 0,
                    1 if row["review_required"] else 0,
                    row["review_reason"],
                    row.get("printer"),
                    row.get("person"),
                    created_at,
                    created_at,
                ),
            )
            row_id = int(cursor.lastrowid)
            inserted_ids.append(row_id)
            _record_event(connection, row_id, "created", created_at, {"status": row["status"]})

        connection.commit()
        return _load_rows_by_ids(connection, inserted_ids)


def _row_to_classification_row(row: sqlite3.Row) -> ClassificationRow:
    dimensions = None
    if row["dimension_x_mm"] is not None:
        dimensions = DimensionSummary(
            x_mm=row["dimension_x_mm"],
            y_mm=row["dimension_y_mm"],
            z_mm=row["dimension_z_mm"],
        )

    row_id = row["id"]
    confidence = row["confidence"]
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    return ClassificationRow(
        row_id=row_id,
        file_name=row["file_name"],
        case_id=row["case_id"],
        model_type=row["model_type"],
        preset=row["preset"],
        confidence=confidence,
        status=row["status"],
        dimensions=dimensions,
        volume_ml=row["volume_ml"],
        structure=row["structure"],
        structure_confidence=row["structure_confidence"],
        structure_reason=row["structure_reason"],
        structure_metrics=json.loads(row["structure_metrics_json"]) if row["structure_metrics_json"] else None,
        structure_locked=bool(row["structure_locked"]),
        review_required=bool(row["review_required"]),
        review_reason=row["review_reason"],
        current_event_at=row["current_event_at"],
        created_at=row["created_at"],
        printer=row["printer"],
        person=row["person"],
        thumbnail_url=f"/api/uploads/rows/{row_id}/thumbnail.svg",
        file_url=f"/api/uploads/rows/{row_id}/file",
        file_path=row["stored_path"],
    )


def _load_rows_by_ids(connection: sqlite3.Connection, row_ids: list[int]) -> list[ClassificationRow]:
    if not row_ids:
        return []
    placeholders = ",".join("?" for _ in row_ids)
    rows = connection.execute(
        f"""
        SELECT *
        FROM upload_rows
        WHERE id IN ({placeholders})
        ORDER BY id
        """,
        tuple(row_ids),
    ).fetchall()
    return [_row_to_classification_row(row) for row in rows]


def list_queue_rows(settings: Settings) -> tuple[list[ClassificationRow], list[ClassificationRow]]:
    with closing(connect(settings)) as connection:
        active_rows = connection.execute(
            """
            SELECT *
            FROM upload_rows
            WHERE status NOT IN ('Submitted', 'Printed')
            ORDER BY
                CASE WHEN case_id IS NULL OR case_id = '' THEN 1 ELSE 0 END,
                case_id COLLATE NOCASE,
                created_at,
                id
            """
        ).fetchall()
        processed_rows = connection.execute(
            """
            SELECT *
            FROM upload_rows
            WHERE status IN ('Submitted', 'Printed')
            ORDER BY current_event_at DESC, id DESC
            """
        ).fetchall()
        return (
            [_row_to_classification_row(row) for row in active_rows],
            [_row_to_classification_row(row) for row in processed_rows],
        )


def find_duplicate_hashes(settings: Settings, content_hashes: Iterable[str]) -> set[str]:
    hash_list = [content_hash for content_hash in content_hashes if content_hash]
    if not hash_list:
        return set()

    placeholders = ",".join("?" for _ in hash_list)
    with closing(connect(settings)) as connection:
        rows = connection.execute(
            f"""
            SELECT DISTINCT content_hash
            FROM upload_rows
            WHERE content_hash IN ({placeholders})
            AND status IN ('Ready', 'Check', 'Needs Review', 'Duplicate', 'Submitted', 'Printed')
            """,
            tuple(hash_list),
        ).fetchall()
        return {row["content_hash"] for row in rows if row["content_hash"]}


def update_upload_row(
    settings: Settings,
    row_id: int,
    model_type: str | None,
    preset: str | None,
) -> ClassificationRow | None:
    with closing(connect(settings)) as connection:
        existing = connection.execute(
            """
            SELECT *
            FROM upload_rows
            WHERE id = ?
            """,
            (row_id,),
        ).fetchone()
        if existing is None:
            return None
        if existing["status"] in {"Submitted", "Printed"}:
            raise ValueError("Submitted rows are read-only.")

        preset = _normalize_manual_preset(model_type, preset)
        status = existing["status"]
        if status not in {"Duplicate", "Submitted", "Printed"}:
            status = derive_status(existing["confidence"], model_type, preset, manual_override=True)

        next_structure = existing["structure"]
        next_structure_confidence = existing["structure_confidence"]
        next_structure_reason = existing["structure_reason"]
        next_structure_metrics_json = existing["structure_metrics_json"]
        next_structure_locked = bool(existing["structure_locked"])
        next_review_required = bool(existing["review_required"])
        next_review_reason = existing["review_reason"]

        if model_type == "Ortho - Solid":
            next_structure = "solid"
            next_structure_confidence = existing["confidence"]
            next_structure_reason = "Manual model type override locked structure to Ortho - Solid."
            next_structure_locked = True
        elif model_type == "Ortho - Hollow":
            next_structure = "hollow"
            next_structure_confidence = existing["confidence"]
            next_structure_reason = "Manual model type override locked structure to Ortho - Hollow."
            next_structure_locked = True

        if status == "Ready" and model_type and preset:
            next_review_required = False
            next_review_reason = None

        connection.execute(
            """
            UPDATE upload_rows
            SET model_type = ?, preset = ?, status = ?, structure = ?, structure_confidence = ?,
                structure_reason = ?, structure_metrics_json = ?, structure_locked = ?,
                review_required = ?, review_reason = ?,
                current_event_at = COALESCE(current_event_at, created_at)
            WHERE id = ?
            """,
            (
                model_type,
                preset,
                status,
                next_structure,
                next_structure_confidence,
                next_structure_reason,
                next_structure_metrics_json,
                1 if next_structure_locked else 0,
                1 if next_review_required else 0,
                next_review_reason,
                row_id,
            ),
        )
        _record_event(
            connection,
            row_id,
            "updated",
            _now_iso(),
            {
                "model_type": model_type,
                "preset": preset,
                "status": status,
                "structure": next_structure,
                "structure_locked": next_structure_locked,
            },
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT *
            FROM upload_rows
            WHERE id = ?
            """,
            (row_id,),
        ).fetchone()
        return _row_to_classification_row(row) if row else None


def bulk_update_upload_rows(
    settings: Settings,
    row_ids: Iterable[int],
    model_type: str | None,
    preset: str | None,
) -> list[ClassificationRow]:
    ids = list(row_ids)
    if not ids:
        return []

    now = _now_iso()
    with closing(connect(settings)) as connection:
        rows = {
            row["id"]: row
            for row in connection.execute(
                f"""
                SELECT *
                FROM upload_rows
                WHERE id IN ({",".join("?" for _ in ids)})
                """,
                tuple(ids),
            ).fetchall()
        }

        if any(row["status"] in {"Submitted", "Printed"} for row in rows.values()):
            raise ValueError("Submitted rows are read-only.")

        for row_id in ids:
            row = rows.get(row_id)
            if row is None:
                continue

            next_model_type = model_type if model_type is not None else row["model_type"]
            if model_type is not None and preset is None:
                raw_preset = model_type
            else:
                raw_preset = preset if preset is not None else row["preset"]
            next_preset = _normalize_manual_preset(next_model_type, raw_preset)
            next_status = row["status"]
            if next_status not in {"Duplicate", "Submitted", "Printed"}:
                next_status = derive_status(row["confidence"], next_model_type, next_preset, manual_override=True)

            next_structure = row["structure"]
            next_structure_confidence = row["structure_confidence"]
            next_structure_reason = row["structure_reason"]
            next_structure_metrics_json = row["structure_metrics_json"]
            next_structure_locked = bool(row["structure_locked"])
            next_review_required = bool(row["review_required"])
            next_review_reason = row["review_reason"]
            if next_model_type == "Ortho - Solid":
                next_structure = "solid"
                next_structure_confidence = row["confidence"]
                next_structure_reason = "Manual model type override locked structure to Ortho - Solid."
                next_structure_locked = True
            elif next_model_type == "Ortho - Hollow":
                next_structure = "hollow"
                next_structure_confidence = row["confidence"]
                next_structure_reason = "Manual model type override locked structure to Ortho - Hollow."
                next_structure_locked = True

            if next_status == "Ready" and next_model_type and next_preset:
                next_review_required = False
                next_review_reason = None

            connection.execute(
                """
                UPDATE upload_rows
                SET model_type = ?, preset = ?, status = ?, structure = ?, structure_confidence = ?,
                    structure_reason = ?, structure_metrics_json = ?, structure_locked = ?,
                    review_required = ?, review_reason = ?,
                    current_event_at = COALESCE(current_event_at, created_at)
                WHERE id = ?
                """,
                (
                    next_model_type,
                    next_preset,
                    next_status,
                    next_structure,
                    next_structure_confidence,
                    next_structure_reason,
                    next_structure_metrics_json,
                    1 if next_structure_locked else 0,
                    1 if next_review_required else 0,
                    next_review_reason,
                    row_id,
                ),
            )
            _record_event(
                connection,
                row_id,
                "bulk_updated",
                now,
                {
                    "model_type": next_model_type,
                    "preset": next_preset,
                    "status": next_status,
                    "structure": next_structure,
                    "structure_locked": next_structure_locked,
                },
            )

        connection.commit()
        return _load_rows_by_ids(connection, ids)


def allow_duplicate_rows(settings: Settings, row_ids: Iterable[int]) -> list[ClassificationRow]:
    ids = list(row_ids)
    now = _now_iso()
    with closing(connect(settings)) as connection:
        for row_id in ids:
            row = connection.execute("SELECT * FROM upload_rows WHERE id = ?", (row_id,)).fetchone()
            if row is None or row["status"] != "Duplicate":
                continue
            next_status = derive_status(row["confidence"], row["model_type"], row["preset"], manual_override=True)
            connection.execute(
                """
                UPDATE upload_rows
                SET status = ?, current_event_at = ?
                WHERE id = ?
                """,
                (next_status, now, row_id),
            )
            _record_event(connection, row_id, "allow_duplicate", now, {"status": next_status})

        connection.commit()
        return _load_rows_by_ids(connection, ids)


def send_rows_to_print(settings: Settings, row_ids: Iterable[int]) -> list[ClassificationRow]:
    ids = list(row_ids)
    now = _now_iso()
    with closing(connect(settings)) as connection:
        for row_id in ids:
            row = connection.execute("SELECT * FROM upload_rows WHERE id = ?", (row_id,)).fetchone()
            if row is None or row["status"] != "Ready":
                continue
            connection.execute(
                """
                UPDATE upload_rows
                SET status = 'Submitted', current_event_at = ?
                WHERE id = ?
                """,
                (now, row_id),
            )
            _record_event(connection, row_id, "submitted", now, {"status": "Submitted"})

        connection.commit()
        return _load_rows_by_ids(connection, ids)


def bulk_delete_upload_rows(settings: Settings, row_ids: Iterable[int]) -> list[int]:
    ids = list(row_ids)
    if not ids:
        return []

    with closing(connect(settings)) as connection:
        rows = {
            row["id"]: row
            for row in connection.execute(
                f"""
                SELECT id, stored_path, session_id, status
                FROM upload_rows
                WHERE id IN ({",".join("?" for _ in ids)})
                """,
                tuple(ids),
            ).fetchall()
        }

        if any(row["status"] in {"Submitted", "Printed"} for row in rows.values()):
            raise ValueError("Submitted rows cannot be deleted.")

        deleted_ids: list[int] = []
        affected_sessions: set[str] = set()
        for row_id in ids:
            row = rows.get(row_id)
            if row is None:
                continue

            stored_path = Path(row["stored_path"])
            if stored_path.exists():
                stored_path.unlink(missing_ok=True)

            connection.execute("DELETE FROM upload_rows WHERE id = ?", (row_id,))
            deleted_ids.append(row_id)
            affected_sessions.add(row["session_id"])

        for session_id in affected_sessions:
            remaining_in_session = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM upload_rows
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if remaining_in_session and remaining_in_session["count"] == 0:
                connection.execute("DELETE FROM upload_sessions WHERE session_id = ?", (session_id,))
                session_dir = settings.uploads_dir / session_id
                if session_dir.exists():
                    session_dir.rmdir()

        connection.commit()
        return deleted_ids


def delete_upload_row(settings: Settings, row_id: int) -> bool:
    with closing(connect(settings)) as connection:
        row = connection.execute(
            """
            SELECT id, stored_path, session_id, status
            FROM upload_rows
            WHERE id = ?
            """,
            (row_id,),
        ).fetchone()
        if row is None:
            return False
        if row["status"] in {"Submitted", "Printed"}:
            raise ValueError("Submitted rows cannot be deleted.")

        stored_path = Path(row["stored_path"])
        if stored_path.exists():
            stored_path.unlink(missing_ok=True)

        connection.execute("DELETE FROM upload_rows WHERE id = ?", (row_id,))
        remaining_in_session = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM upload_rows
            WHERE session_id = ?
            """,
            (row["session_id"],),
        ).fetchone()
        if remaining_in_session and remaining_in_session["count"] == 0:
            connection.execute("DELETE FROM upload_sessions WHERE session_id = ?", (row["session_id"],))
            session_dir = settings.uploads_dir / row["session_id"]
            if session_dir.exists():
                session_dir.rmdir()
        connection.commit()
        return True


def get_stored_file_path(settings: Settings, row_id: int) -> Path | None:
    with closing(connect(settings)) as connection:
        row = connection.execute(
            """
            SELECT stored_path
            FROM upload_rows
            WHERE id = ?
            """,
            (row_id,),
        ).fetchone()
        if row is None:
            return None
        return Path(row["stored_path"])


def get_upload_row_by_id(settings: Settings, row_id: int) -> ClassificationRow | None:
    with closing(connect(settings)) as connection:
        row = connection.execute(
            "SELECT * FROM upload_rows WHERE id = ?",
            (row_id,),
        ).fetchone()
        return _row_to_classification_row(row) if row else None


def get_thumbnail_svg(settings: Settings, row_id: int) -> str | None:
    with closing(connect(settings)) as connection:
        row = connection.execute(
            """
            SELECT stored_path, content_hash, thumbnail_svg
            FROM upload_rows
            WHERE id = ?
            """,
            (row_id,),
        ).fetchone()
        if row is None:
            return None
        if is_current_thumbnail_svg(row["thumbnail_svg"]):
            return row["thumbnail_svg"]

        if row["content_hash"]:
            cached = connection.execute(
                """
                SELECT thumbnail_svg
                FROM upload_rows
                WHERE content_hash = ?
                AND thumbnail_svg IS NOT NULL
                AND thumbnail_svg != ''
                AND id != ?
                ORDER BY id
                LIMIT 1
                """,
                (row["content_hash"], row_id),
            ).fetchone()
            if cached and is_current_thumbnail_svg(cached["thumbnail_svg"]):
                connection.execute(
                    "UPDATE upload_rows SET thumbnail_svg = ? WHERE id = ?",
                    (cached["thumbnail_svg"], row_id),
                )
                connection.commit()
                return cached["thumbnail_svg"]

        stored_path = Path(row["stored_path"])
        if not stored_path.exists():
            return None

        svg = generate_thumbnail_svg(stored_path)
        connection.execute(
            "UPDATE upload_rows SET thumbnail_svg = ? WHERE id = ?",
            (svg, row_id),
        )
        connection.commit()
        return svg
