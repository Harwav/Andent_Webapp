"""Phase 1: Windows EXE packaging tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import build_settings
from app.version import __version__


def test_output_dir_can_be_overridden_for_packaged_runtime(tmp_path, monkeypatch):
    output_dir = tmp_path / "dist-output"
    data_dir = tmp_path / "data"
    monkeypatch.setenv("FORMFLOW_WEB_OUTPUT_DIR", str(output_dir))

    settings = build_settings(data_dir=data_dir, database_path=data_dir / "formflow.db")

    assert settings.output_dir == output_dir


def test_application_version_uses_semver_triplet():
    parts = __version__.split(".")

    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
