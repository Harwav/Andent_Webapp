from __future__ import annotations

import logging
import os
from pathlib import Path


def appdata_log_dir() -> Path:
    appdata = os.environ.get("APPDATA") or Path.home()
    log_dir = Path(appdata) / "Andent Web" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def configure_logging(level: int = logging.INFO) -> Path:
    log_dir = appdata_log_dir()
    log_path = log_dir / "andent.log"

    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(file_handler)

    return log_path
