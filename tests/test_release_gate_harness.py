import json

import pytest

from scripts.release_gate.evidence import EvidenceStore, StageResult, build_dataset_manifest
from scripts.release_gate.preform_probe import is_virtual_device
from scripts.release_gate.run_release_gate import build_parser, default_evidence_dir
from scripts.release_gate.stages import build_stage_plan, command_name, validate_dataset
from scripts.release_gate.verdict import render_verdict


def test_evidence_store_writes_stage_json(tmp_path):
    store = EvidenceStore(tmp_path)
    result = StageResult(
        stage="environment",
        status="pass",
        duration_seconds=1.25,
        command="python --version",
        artifacts=["environment.json"],
        notes=["ok"],
    )

    store.write_stage_result(result)

    payload = json.loads((tmp_path / "environment.json").read_text(encoding="utf-8"))
    assert payload["stage"] == "environment"
    assert payload["status"] == "pass"
    assert payload["duration_seconds"] == 1.25
    assert payload["command"] == "python --version"
    assert payload["artifacts"] == ["environment.json"]
    assert payload["notes"] == ["ok"]


def test_dataset_manifest_hashes_stl_files(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    first = dataset / "A.stl"
    second = dataset / "B.stl"
    first.write_bytes(b"solid a\nendsolid a\n")
    second.write_bytes(b"solid b\nendsolid b\n")

    manifest = build_dataset_manifest(dataset, git_commit="abc123")

    assert manifest["source_path"] == str(dataset.resolve())
    assert manifest["stl_count"] == 2
    assert manifest["git_commit"] == "abc123"
    assert [item["name"] for item in manifest["files"]] == ["A.stl", "B.stl"]
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])
    assert manifest["total_bytes"] == first.stat().st_size + second.stat().st_size


def test_verdict_requires_all_stages_pass():
    markdown = render_verdict(
        stage_results=[
            StageResult("environment", "pass", 1.0, "env", [], []),
            StageResult("backend", "fail", 2.0, "pytest", ["pytest.log"], ["1 failed"]),
        ],
        metadata={
            "git_commit": "abc123",
            "dataset_path": "C:/data",
            "stl_count": 91,
            "preform_url": "http://127.0.0.1:44388",
        },
    )

    assert "SHIP: no" in markdown
    assert "| backend | fail |" in markdown
    assert "1 failed" in markdown


def test_validate_dataset_rejects_missing_folder(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_dataset(tmp_path / "missing")


def test_validate_dataset_rejects_folder_without_stls(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="No .stl files"):
        validate_dataset(empty)


def test_validate_dataset_accepts_stl_folder(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "case.stl").write_text("solid case\nendsolid case\n", encoding="utf-8")

    assert validate_dataset(dataset) == dataset.resolve()


def test_is_virtual_device_uses_virtual_debug_signals():
    assert is_virtual_device({"id": "debug", "name": "Virtual Printer", "is_virtual": True})
    assert is_virtual_device({"device_id": "virtual-1", "name": "Debug Form 4BL"})
    assert not is_virtual_device({"device_id": "real-1", "name": "Lab Form 4BL", "is_virtual": False})


def test_parser_uses_canonical_dataset_default(monkeypatch):
    monkeypatch.delenv("FORMFLOW_RELEASE_TEST_DATA_DIR", raising=False)
    args = build_parser().parse_args([])

    assert str(args.test_data_dir).endswith("From 4BL Test Data")
    assert args.preform_url == "http://127.0.0.1:44388"


def test_parser_accepts_dataset_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("FORMFLOW_RELEASE_TEST_DATA_DIR", str(tmp_path))
    args = build_parser().parse_args([])

    assert args.test_data_dir == tmp_path


def test_default_evidence_dir_contains_pre_release_prefix():
    evidence_dir = default_evidence_dir()

    assert "docs" in evidence_dir.parts
    assert "98_VerificationArtifacts" in evidence_dir.parts
    assert evidence_dir.name.startswith("pre_release_")


def test_stage_plan_contains_required_stage_names(tmp_path):
    plan = build_stage_plan(
        evidence_dir=tmp_path,
        test_data_dir=tmp_path,
        preform_url="http://127.0.0.1:44388",
        headed=False,
        skip_package_build=False,
    )

    assert [stage.name for stage in plan] == [
        "environment",
        "static",
        "backend",
        "browser-mocked",
        "browser-live-app",
        "live-preform-virtual",
        "packaged-runtime",
    ]


def test_stage_plan_keeps_skip_package_build_out_of_playwright_args(tmp_path):
    plan = build_stage_plan(
        evidence_dir=tmp_path,
        test_data_dir=tmp_path,
        preform_url="http://127.0.0.1:44388",
        headed=True,
        skip_package_build=True,
    )

    packaged = next(stage for stage in plan if stage.name == "packaged-runtime")
    assert "--skip-package-build" not in packaged.command
    assert packaged.env["FORMFLOW_RELEASE_SKIP_PACKAGE_BUILD"] == "1"


def test_stage_plan_disables_external_pytest_plugins(tmp_path):
    plan = build_stage_plan(
        evidence_dir=tmp_path,
        test_data_dir=tmp_path,
        preform_url="http://127.0.0.1:44388",
        headed=False,
        skip_package_build=False,
    )

    backend = next(stage for stage in plan if stage.name == "backend")
    assert backend.env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert "FORMFLOW_WEB_PRINT_DISPATCH_MODE" not in backend.env


def test_stage_plan_limits_virtual_dispatch_to_live_stages(tmp_path):
    plan = build_stage_plan(
        evidence_dir=tmp_path,
        test_data_dir=tmp_path,
        preform_url="http://127.0.0.1:44388",
        headed=False,
        skip_package_build=False,
    )

    live_stage_names = {"browser-live-app", "live-preform-virtual", "packaged-runtime"}
    for stage in plan:
        if stage.name in live_stage_names:
            assert stage.env["FORMFLOW_WEB_PRINT_DISPATCH_MODE"] == "virtual"
        else:
            assert "FORMFLOW_WEB_PRINT_DISPATCH_MODE" not in stage.env


def test_command_name_uses_windows_cmd_shim(monkeypatch):
    monkeypatch.setattr("scripts.release_gate.stages.os.name", "nt")

    assert command_name("npx") == "npx.cmd"
    assert command_name("python") == "python"


def test_browser_mocked_stage_runs_serially_with_actionable_timeout(tmp_path):
    plan = build_stage_plan(
        evidence_dir=tmp_path,
        test_data_dir=tmp_path,
        preform_url="http://127.0.0.1:44388",
        headed=False,
        skip_package_build=False,
    )

    stage = next(stage for stage in plan if stage.name == "browser-mocked")
    assert "--workers=1" in stage.command
    assert stage.timeout_seconds >= 1200
