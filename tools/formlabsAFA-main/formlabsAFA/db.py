from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Iterable, Self
from uuid import UUID, uuid4

import aiosqlite
from pydantic import BaseModel


class ModelId(UUID):
    pass


class ModelStatusEnum(str, Enum):
    REGISTERED = "registered"
    BATCHED = "batched"
    HOLLOWED = "hollowed"
    ENQUEUED = "enqueued"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelStatus(BaseModel):
    value: ModelStatusEnum
    job_name: str | None = None
    printer_serial: str | None = None
    error_message: str | None = None


_UUID_REGEX = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_MODEL_FILENAME_RE = re.compile(f"(.*)_({_UUID_REGEX}).stl")


def join_model_filename(model_id: ModelId, original_name: str) -> str:
    return f"{original_name}_{model_id}.stl"


def split_model_filename(filename: str) -> tuple[ModelId, str]:
    match = _MODEL_FILENAME_RE.match(filename)
    if match is None:
        raise ValueError(f"Invalid model filename: {filename}")
    return ModelId(hex=match.group(2)), match.group(1)


class Database:
    MODELS_TABLE_SCHEMA = (
        "id BLOB PRIMARY KEY, status TEXT, original_path BLOB, job_name TEXT, "
        "metadata TEXT, priority TEXT DEFAULT 'normal', callback_url TEXT, "
        "printer_serial TEXT, created_at TEXT, completed_at TEXT, error_message TEXT"
    )

    @dataclass
    class Row:
        id: ModelId
        status: ModelStatus
        original_path: Path

    @classmethod
    async def connect_or_initialize(cls, db_path: Path) -> Self:
        db_connection = await aiosqlite.connect(db_path)
        db_connection.row_factory = aiosqlite.Row
        async with db_connection.execute(
            f"CREATE TABLE IF NOT EXISTS models ({cls.MODELS_TABLE_SCHEMA})"
        ):
            await db_connection.commit()
        return cls(db_connection)

    def __init__(self, connection: aiosqlite.Connection):
        self.connection = connection

    async def close(self) -> None:
        await self.connection.close()

    async def register_model(
        self,
        path: Path,
        metadata: str | None = None,
        priority: str = "normal",
        callback_url: str | None = None,
    ) -> ModelId:
        model_uuid = ModelId(bytes_le=uuid4().bytes_le)
        now = datetime.now().isoformat()
        async with self.connection.execute(
            "INSERT INTO models (id, status, original_path, job_name, metadata, priority, callback_url, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (model_uuid.bytes_le, ModelStatusEnum.REGISTERED, bytes(path), None, metadata, priority, callback_url, now),
        ):
            await self.connection.commit()
        return model_uuid

    async def _get_row(self, model_id: ModelId) -> Row | None:
        async with self.connection.execute(
            "SELECT * FROM models WHERE id = ?",
            (model_id.bytes_le,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return Database.Row(
                id=ModelId(bytes_le=row["id"]),
                status=ModelStatus(value=row["status"], job_name=row["job_name"]),
                original_path=Path(row["original_path"].decode()),
            )

    async def get_model_status(self, model_id: ModelId) -> ModelStatus | None:
        if (row := await self._get_row(model_id)) is None:
            return None
        return row.status

    async def set_model_status(self, model_id: ModelId, status: ModelStatus) -> None:
        if status.value not in list(ModelStatusEnum):
            raise ValueError(f"Invalid status: {status.value}")
        completed_at = datetime.now().isoformat() if status.value in (
            ModelStatusEnum.COMPLETED, ModelStatusEnum.FAILED
        ) else None
        await self.connection.execute(
            "UPDATE models SET status = ?, job_name = ?, printer_serial = ?, "
            "error_message = ?, completed_at = COALESCE(?, completed_at) WHERE id = ?",
            (status.value, status.job_name, status.printer_serial,
             status.error_message, completed_at, model_id.bytes_le),
        )
        await self.connection.commit()

    async def set_model_statuses_bulk(
        self, model_ids: Iterable[ModelId], status: ModelStatus
    ) -> None:
        if status.value not in list(ModelStatusEnum):
            raise ValueError(f"Invalid status: {status.value}")
        for model_id in model_ids:
            await self.connection.execute(
                "UPDATE models SET status = ?, job_name = ? WHERE id = ?",
                (status.value, status.job_name, model_id.bytes_le),
            )
        await self.connection.commit()

    async def get_model_name(self, model_id: ModelId) -> str | None:
        if (row := await self._get_row(model_id)) is None:
            return None
        return row.original_path.stem
