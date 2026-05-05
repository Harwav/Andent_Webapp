from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release_gate.evidence import EvidenceStore, StageResult, build_dataset_manifest
from scripts.release_gate.preform_probe import probe_preform
from scripts.release_gate.stages import build_stage_plan, validate_dataset
from scripts.release_gate.verdict import write_verdict


CANONICAL_DATASET = Path(r"C:\Users\Marcus\Desktop\From 4BL Test Data")
DEFAULT_PREFORM_URL = "http://127.0.0.1:44388"


def default_evidence_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("docs/02_planning/98_VerificationArtifacts") / f"pre_release_{stamp}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the hard FormFlow release gate.")
    parser.add_argument("mode", nargs="?", default="all", choices=["all", "environment-only"])
    parser.add_argument(
        "--test-data-dir",
        type=Path,
        default=Path(os.environ.get("FORMFLOW_RELEASE_TEST_DATA_DIR", CANONICAL_DATASET)),
    )
    parser.add_argument("--preform-url", default=os.environ.get("PREFORM_SERVER_URL", DEFAULT_PREFORM_URL))
    parser.add_argument("--evidence-dir", type=Path, default=default_evidence_dir())
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--skip-package-build", action="store_true")
    return parser


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except subprocess.CalledProcessError:
        return "unknown"


def run_environment(args: argparse.Namespace, store: EvidenceStore) -> StageResult:
    started = time.monotonic()
    notes: list[str] = []
    dataset_dir = validate_dataset(args.test_data_dir)
    commit = git_commit()
    store.write_json("dataset-manifest.json", build_dataset_manifest(dataset_dir, git_commit=commit))
    preform = probe_preform(args.preform_url)
    store.write_json("preform-status.json", preform)
    with store.path("git-status.txt").open("w", encoding="utf-8") as status_file:
        subprocess.run(["git", "status", "--short"], text=True, stdout=status_file, check=False)
    status = "pass" if preform.get("reachable") else "fail"
    if status == "fail":
        notes.append(str(preform.get("error", "PreFormServer probe failed")))
    result = StageResult(
        "environment",
        status,
        round(time.monotonic() - started, 3),
        "environment probes",
        ["dataset-manifest.json", "preform-status.json", "git-status.txt"],
        notes,
    )
    store.write_stage_result(result)
    return result


def run_command(stage, store: EvidenceStore) -> StageResult:
    started = time.monotonic()
    log_path = store.path(stage.log_name or f"{stage.name}.log")
    env = {**os.environ, **stage.env}
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            stage.command,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=stage.timeout_seconds,
            env=env,
            check=False,
        )
    status = "pass" if completed.returncode == 0 else "fail"
    result = StageResult(
        stage.name,
        status,
        round(time.monotonic() - started, 3),
        " ".join(stage.command),
        [log_path.name],
        [] if status == "pass" else [f"exit code {completed.returncode}"],
    )
    store.write_stage_result(result)
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = EvidenceStore(args.evidence_dir)
    results = [run_environment(args, store)]
    if args.mode == "all" and results[0].status == "pass":
        for stage in build_stage_plan(
            evidence_dir=args.evidence_dir,
            test_data_dir=args.test_data_dir,
            preform_url=args.preform_url,
            headed=args.headed,
            skip_package_build=args.skip_package_build,
        ):
            if stage.name == "environment":
                continue
            results.append(run_command(stage, store))
            if results[-1].status != "pass":
                break
    metadata = {
        "git_commit": git_commit(),
        "dataset_path": str(args.test_data_dir),
        "preform_url": args.preform_url,
    }
    dataset_manifest_path = store.path("dataset-manifest.json")
    if dataset_manifest_path.exists():
        metadata["stl_count"] = json.loads(
            dataset_manifest_path.read_text(encoding="utf-8")
        ).get("stl_count")
    write_verdict(store, stage_results=results, metadata=metadata)
    return 0 if all(result.status == "pass" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
