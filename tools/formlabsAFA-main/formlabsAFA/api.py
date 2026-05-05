from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Literal, Union

import aiohttp
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

from formlabsAFA.context import AppContext
from formlabsAFA.db import Database, ModelId, ModelStatus

logger = logging.getLogger("formlabsAFA.api")


class ModelStatusFoundResponse(BaseModel):
    status: Literal["OK"] = "OK"
    model_status: ModelStatus


class ModelStatusNotFoundResponse(BaseModel):
    status: Literal["NOT_FOUND"] = "NOT_FOUND"


class ModelStatusInvalidIdResponse(BaseModel):
    status: Literal["INVALID_MODEL_ID"] = "INVALID_MODEL_ID"


ModelStatusResponse = Annotated[
    Union[
        ModelStatusFoundResponse,
        ModelStatusNotFoundResponse,
        ModelStatusInvalidIdResponse,
    ],
    Field(discriminator="status"),
]


class JobSubmission(BaseModel):
    stl_paths: list[str]
    metadata: dict | None = None
    priority: str = "normal"
    preferred_printer: str | None = None
    callback_url: str | None = None


def create_app(ctx: AppContext) -> FastAPI:
    app = FastAPI(title="formlabsAFA", version="2.0")

    # ---- Health ----

    @app.get("/health-check")
    async def health_check() -> dict[str, str]:
        return {"status": "OK"}

    # ---- Jobs (new MES-friendly endpoints) ----

    @app.post("/jobs")
    async def submit_job(job: JobSubmission) -> dict:
        from formlabsAFA.db import join_model_filename
        import shutil
        from pathlib import Path

        metadata_json = json.dumps(job.metadata) if job.metadata else None
        results: dict[str, str | None] = {}

        for stl_path in job.stl_paths:
            path = Path(stl_path)
            if not path.is_file():
                logger.warning("Job submission: file not found: %s", stl_path)
                results[stl_path] = None
                continue

            model_id = await ctx.db.register_model(
                path,
                metadata=metadata_json,
                priority=job.priority,
                callback_url=job.callback_url,
            )
            model_name = await ctx.db.get_model_name(model_id)
            if model_name is None:
                results[stl_path] = None
                continue

            out_name = join_model_filename(model_id, model_name)
            out_path = ctx.workspace.stl_input / out_name
            shutil.copy(path, out_path)
            results[stl_path] = str(model_id)
            logger.info("Job registered: %s → %s (priority=%s)", stl_path, model_id, job.priority)

        return {
            "models": results,
            "priority": job.priority,
            "callback_url": job.callback_url,
        }

    @app.get("/jobs/{model_id}")
    async def get_job(model_id: str) -> dict:
        try:
            mid = ModelId(model_id)
        except ValueError:
            return {"status": "INVALID_MODEL_ID"}
        status = await ctx.db.get_model_status(mid)
        if status is None:
            return {"status": "NOT_FOUND"}
        return {"status": "OK", "model_status": status.model_dump()}

    @app.get("/queue")
    async def get_queue() -> dict:
        queue = ctx.model_queue
        return {
            "pending": queue.count if queue else 0,
            "batch_counter": ctx.batch_counter.current,
        }

    # ---- Legacy endpoints (backward compatible) ----

    @app.post("/register-models")
    async def register_models(stl_paths: list[str]) -> dict[str, str | None]:
        from formlabsAFA.db import join_model_filename
        import shutil
        from pathlib import Path

        results: dict[str, str | None] = {}
        for stl_path in stl_paths:
            path = Path(stl_path)
            model_id = await ctx.db.register_model(path)
            model_name = await ctx.db.get_model_name(model_id)
            if model_name is None:
                results[stl_path] = None
                continue
            out_name = join_model_filename(model_id, model_name)
            out_path = ctx.workspace.stl_input / out_name
            shutil.copy(path, out_path)
            results[stl_path] = str(model_id)
        return results

    @app.post("/models-status")
    async def models_status(
        model_ids: list[str],
    ) -> dict[str, ModelStatusResponse]:
        async def lookup(raw_id: str) -> tuple[str, ModelStatusResponse]:
            try:
                model_uuid = ModelId(raw_id)
            except ValueError:
                return raw_id, ModelStatusInvalidIdResponse()
            status = await ctx.db.get_model_status(model_uuid)
            if status is None:
                return raw_id, ModelStatusNotFoundResponse()
            return raw_id, ModelStatusFoundResponse(model_status=status)

        pairs = await asyncio.gather(*(lookup(rid) for rid in model_ids))
        return dict(pairs)

    # ---- Printers & Materials (Dashboard API) ----

    @app.get("/printers")
    async def list_printers() -> list[dict]:
        dashboard = getattr(ctx, "dashboard_client", None)
        if not dashboard:
            return []
        return dashboard.get_all_printers()

    @app.get("/printers/{serial}")
    async def get_printer(serial: str) -> dict:
        dashboard = getattr(ctx, "dashboard_client", None)
        if not dashboard:
            return {"error": "Dashboard API not configured"}
        result = dashboard.get_printer_dict(serial)
        if not result:
            return {"error": "Printer not found"}
        return result

    @app.get("/materials")
    async def list_materials() -> list[dict]:
        dashboard = getattr(ctx, "dashboard_client", None)
        if not dashboard:
            return []
        return dashboard.get_all_cartridges()

    return app
