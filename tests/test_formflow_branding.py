"""Branding regression tests for FormFlow product-facing surfaces."""

from pathlib import Path

from app.config import build_settings


LEGACY_BRAND = "An" + "dent"


def test_main_page_uses_formflow_without_byline():
    index_html = Path("app/static/index.html").read_text(encoding="utf-8")

    assert "<title>FormFlow - STL Intake Queue</title>" in index_html
    assert '<span class="site-logo-name">FormFlow</span>' in index_html
    assert "by FormFlow" not in index_html
    assert LEGACY_BRAND not in index_html


def test_default_app_identity_is_formflow(tmp_path, monkeypatch):
    monkeypatch.setenv("FORMFLOW_WEB_APPDATA_DIR", str(tmp_path / "appdata"))

    settings = build_settings(
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "formflow.db",
    )

    assert settings.app_name == "FormFlow"
    assert settings.preform_managed_dir == tmp_path / "appdata" / "FormFlow" / "PreFormServer"


def test_exe_launch_strategy_uses_formflow_branding():
    strategy_files = [
        Path("docs/superpowers/specs/2026-04-28-phase1-exe-packaging-design.md"),
        Path("docs/superpowers/specs/2026-04-29-windows-exe-deployment-design.md"),
        Path("docs/superpowers/plans/2026-04-29-windows-exe-deployment.md"),
    ]

    for strategy_file in strategy_files:
        content = strategy_file.read_text(encoding="utf-8")
        assert "FormFlow" in content
        assert LEGACY_BRAND not in content
