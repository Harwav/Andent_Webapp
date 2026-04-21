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
    appdata_dir: Path
    database_path: Path
    preform_server_port: int
    preform_managed_dir: Path
    preform_managed_executable: Path
    preform_server_url: str
    preform_server_startup_timeout_s: int
    preform_server_shutdown_timeout_s: int
    preform_min_zip_size_bytes: int
    preform_min_supported_version: str
    preform_max_supported_version: str | None
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
    appdata_override = os.getenv("ANDENT_WEB_APPDATA_DIR")
    if appdata_override:
        resolved_appdata_root = Path(appdata_override)
    elif data_dir is not None:
        resolved_appdata_root = resolved_data_dir / "appdata"
    else:
        resolved_appdata_root = Path(os.getenv("APPDATA", resolved_data_dir / "appdata"))

    managed_appdata_dir = resolved_appdata_root / "Andent Web"
    preform_server_port = int(os.getenv("ANDENT_WEB_PREFORM_PORT", "44388"))
    preform_managed_dir = managed_appdata_dir / "PreFormServer"

    return Settings(
        app_name="Andent Web",
        server_host=os.getenv("ANDENT_WEB_HOST", "127.0.0.1"),
        server_port=int(os.getenv("ANDENT_WEB_PORT", "8090")),
        project_root=repo_root,
        data_dir=resolved_data_dir,
        uploads_dir=resolved_data_dir / "uploads",
        static_dir=app_dir / "static",
        appdata_dir=managed_appdata_dir,
        database_path=resolved_database_path,
        preform_server_port=preform_server_port,
        preform_managed_dir=preform_managed_dir,
        preform_managed_executable=preform_managed_dir / "PreFormServer.exe",
        preform_server_url=os.getenv(
            "PREFORM_SERVER_URL",
            f"http://localhost:{preform_server_port}",
        ),
        preform_server_startup_timeout_s=int(
            os.getenv("ANDENT_WEB_PREFORM_STARTUP_TIMEOUT_S", "30")
        ),
        preform_server_shutdown_timeout_s=int(
            os.getenv("ANDENT_WEB_PREFORM_SHUTDOWN_TIMEOUT_S", "10")
        ),
        preform_min_zip_size_bytes=int(
            os.getenv("ANDENT_WEB_PREFORM_MIN_ZIP_SIZE_BYTES", str(10 * 1024 * 1024))
        ),
        preform_min_supported_version=os.getenv(
            "ANDENT_WEB_PREFORM_MIN_VERSION",
            "3.55.0",
        ),
        preform_max_supported_version=os.getenv("ANDENT_WEB_PREFORM_MAX_VERSION") or None,
        formlabs_api_token=os.getenv("FORMLABS_API_TOKEN"),
        formlabs_api_url=os.getenv("FORMLABS_API_URL", "https://api.formlabs.com/v1"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return build_settings()
