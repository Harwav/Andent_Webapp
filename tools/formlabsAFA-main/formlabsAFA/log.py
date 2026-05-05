from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

console = Console()


def tprint(*args, **kwargs) -> None:
    """console.print with a timestamp prefix."""
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(f"[dim][{ts}][/dim]", *args, **kwargs)


def setup_logging(level: str = "INFO", log_dir: Path | None = None) -> None:
    root = logging.getLogger("formlabsAFA")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Rich console handler -- pretty output for operators
    console_level = logging.DEBUG if level.upper() == "DEBUG" else logging.INFO
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
        level=console_level,
    )
    root.addHandler(rich_handler)

    # File handler -- detailed logs (always captures DEBUG for audit trail)
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler = logging.FileHandler(log_dir / "formlabsAFA.log")
        file_handler.setFormatter(fmt)
        file_handler.setLevel(logging.DEBUG)
        root.addHandler(file_handler)


def get_batch_logger(batch_number: int, log_dir: Path) -> logging.Logger:
    """Create a per-batch log file with ISO-friendly timestamps.

    These logs serve as the audit trail for ISO 13485 traceability.
    Each batch log records: input filenames, processing steps,
    output .form file, and any errors or removed models.
    """
    logger = logging.getLogger(f"formlabsAFA.batch.{batch_number}")
    if not logger.handlers:
        log_dir.mkdir(parents=True, exist_ok=True)
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        fh = logging.FileHandler(log_dir / f"batch-{batch_number}.log")
        fh.setFormatter(fmt)
        fh.setLevel(logging.DEBUG)
        logger.addHandler(fh)
    return logger
