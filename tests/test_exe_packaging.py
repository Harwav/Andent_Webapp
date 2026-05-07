"""Phase 1: Windows EXE packaging tests."""

from __future__ import annotations

from dataclasses import replace
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


def test_material_catalog_has_packaged_resource_fallback(tmp_path):
    from app.routers import preform_setup

    preform_setup._MATERIAL_LABEL_CACHE = None
    settings = build_settings(
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "formflow.db",
    )
    settings = replace(settings, project_root=tmp_path)

    mapping = preform_setup._material_label_map(settings)

    assert mapping["FLTO1502"] == "Tough 1500 V2"
    assert mapping["FLBMAM01"] == "BioMed Amber V1"


def test_pyinstaller_spec_bundles_runtime_resources():
    spec_text = Path("formflow.spec").read_text(encoding="utf-8")

    assert '("app/static", "app/static")' in spec_text
    assert '("app/resources", "app/resources")' in spec_text
    assert Path("app/resources/preform-list-materials-latest.json").is_file()
