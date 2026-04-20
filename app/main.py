from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .database import init_db
from .routers.uploads import router as uploads_router
from .routers.metrics import router as metrics_router


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    init_db(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(
        title="Andent Web",
        description="Standalone web intake for Andent Phase 0",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings

    app.mount("/static", StaticFiles(directory=str(resolved_settings.static_dir)), name="static")
    app.include_router(uploads_router)
    app.include_router(metrics_router)

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
