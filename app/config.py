from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str
    server_host: str
    server_port: int
    project_root: Path
    data_dir: Path
    uploads_dir: Path
    static_dir: Path
    database_path: Path
    preform_server_url: str
    formlabs_api_token: str | None
    formlabs_api_url: str


def build_settings(
    *,
    data_dir: Path | None = None,
    database_path: Path | None = None,
) -> Settings:
    # Standalone mode: repo_root is the parent of app/ directory
    app_dir = Path(__file__).resolve().parent  # app/
    repo_root = app_dir.parent  # repository root
    resolved_data_dir = data_dir or Path(
        os.getenv("ANDENT_WEB_DATA_DIR", repo_root / "data")
    )
    resolved_database_path = database_path or Path(
        os.getenv("ANDENT_WEB_DATABASE_PATH", resolved_data_dir / "andent_web.db")
    )

    return Settings(
        app_name="Andent Web",
        server_host=os.getenv("ANDENT_WEB_HOST", "127.0.0.1"),
        server_port=int(os.getenv("ANDENT_WEB_PORT", "8090")),
        project_root=repo_root,
        data_dir=resolved_data_dir,
        uploads_dir=resolved_data_dir / "uploads",
        static_dir=app_dir / "static",
        database_path=resolved_database_path,
        preform_server_url=os.getenv("PREFORM_SERVER_URL", "http://localhost:44388"),
        formlabs_api_token=os.getenv("FORMLABS_API_TOKEN"),
        formlabs_api_url=os.getenv("FORMLABS_API_URL", "https://api.formlabs.com/v1"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return build_settings()
