from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import state as runtime_state
from .config import Settings, get_settings
from .database import init_db
from .routers.metrics import router as metrics_router
from .routers.preform_setup import router as preform_setup_router
from .routers.print_queue import router as print_queue_router
from .routers.setup import router as setup_router
from .routers.uploads import router as uploads_router
from .services.preform_setup_service import PreFormSetupError, PreFormSetupService
from .services.print_queue_service import migrate_print_job_outputs_to_output_dir
from .version import __version__


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    init_db(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_settings.output_dir.mkdir(parents=True, exist_ok=True)
        migrate_print_job_outputs_to_output_dir(resolved_settings)

        async def _autostart_preform():
            try:
                status = await asyncio.to_thread(
                    PreFormSetupService(resolved_settings).start
                )
                logging.info("PreFormServer auto-start: %s", status.readiness)
            except PreFormSetupError as exc:
                logging.info("PreFormServer auto-start skipped: %s", exc)
            except Exception as exc:
                logging.warning("PreFormServer auto-start failed: %s", exc)

        asyncio.create_task(_autostart_preform())
        yield

    app = FastAPI(
        title="FormFlow",
        description="Standalone web intake for FormFlow",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.default_print_dispatch_mode = resolved_settings.print_dispatch_mode
    app.state.lan_ip = runtime_state.LAN_IP

    resolved_settings.output_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(resolved_settings.static_dir)), name="static")
    app.mount("/output", StaticFiles(directory=str(resolved_settings.output_dir)), name="output")
    app.include_router(uploads_router)
    app.include_router(metrics_router)
    app.include_router(preform_setup_router)
    app.include_router(print_queue_router)
    app.include_router(setup_router)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all handler to ensure API errors are always JSON, never HTML."""
        logging.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. Check server logs for details."},
        )

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(resolved_settings.static_dir / "index.html")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/health/live")
    async def health_live() -> dict[str, bool]:
        """Liveness probe - always returns True if server is running."""
        return {"alive": True}

    @app.get("/health/ready")
    async def health_ready() -> dict[str, bool | str]:
        """Readiness probe - checks if server can handle requests."""
        return {"ready": True, "timestamp": datetime.now(timezone.utc).isoformat()}

    @app.get("/metrics", include_in_schema=False)
    async def metrics_dashboard() -> FileResponse:
        return FileResponse(resolved_settings.static_dir / "metrics.html")

    return app


app = create_app()
