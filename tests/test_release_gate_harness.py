import json
from pathlib import Path

from scripts.release_gate.evidence import EvidenceStore, StageResult, build_dataset_manifest
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
