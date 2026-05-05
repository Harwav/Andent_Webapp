# Hard Ship/No-Ship Release Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one hard ship/no-ship release gate that proves backend, browser, packaged runtime, canonical Form 4BL dataset, and live virtual/debug PreFormServer handoff behavior before release.

**Architecture:** Add a Python release-gate harness under `scripts/release_gate/` that orchestrates staged checks, writes evidence JSON, enforces timeouts, and generates a final verdict. Keep Playwright responsible for browser/operator flows, and keep pytest responsible for backend/service invariants. The existing Node release wrapper becomes a compatibility shim that delegates to the Python harness.

**Tech Stack:** Python 3.12, FastAPI, pytest, Node/npm, Playwright Chromium, SQLite, Windows PowerShell, live PreFormServer at `http://127.0.0.1:44388`.

---

## Approved Spec

Implement from:

```text
docs/superpowers/specs/2026-05-05-release-gate-design.md
```

Key user decisions:

- Gate type: hard ship/no-ship.
- Live handoff target: virtual/debug PreForm printers only.
- Canonical dataset: `C:\Users\Marcus\Desktop\From 4BL Test Data`.

## File Structure

Create or modify these files:

```text
scripts/release_gate/__init__.py
scripts/release_gate/run_release_gate.py
scripts/release_gate/stages.py
scripts/release_gate/evidence.py
scripts/release_gate/preform_probe.py
scripts/release_gate/verdict.py
scripts/release_gate/run_release_gate.mjs
tests/test_release_gate_harness.py
tests/release_gate/live_virtual_handoff.spec.ts
tests/release_gate/live_pack_invariants.spec.ts
tests/release_gate/packaged_runtime.spec.ts
tests/release_gate/helpers/page.ts
tests/release_gate/helpers/runtime.ts
tests/release_gate/helpers/python/release_gate_verify.py
package.json
README.md
```

Responsibilities:

- `run_release_gate.py`: CLI entry point, argument parsing, stage sequencing, final exit code.
- `stages.py`: stage definitions and subprocess execution.
- `evidence.py`: evidence directory lifecycle, JSON writes, command logs, dataset manifest hashing.
- `preform_probe.py`: live PreFormServer readiness and device classification helpers.
- `verdict.py`: `release-gate.json` aggregation and `verdict.md` rendering.
- `tests/test_release_gate_harness.py`: fast unit tests for harness behavior.
- Playwright specs: browser, live virtual handoff, pack invariant, and packaged runtime proof.
- `release_gate_verify.py`: DB and PreForm evidence extraction for Playwright.
- `run_release_gate.mjs`: backwards-compatible Node wrapper.

Do not change unrelated app behavior while implementing this plan.

---

### Task 1: Add Evidence And Verdict Primitives

**Files:**
- Create: `scripts/release_gate/__init__.py`
- Create: `scripts/release_gate/evidence.py`
- Create: `scripts/release_gate/verdict.py`
- Create: `tests/test_release_gate_harness.py`

- [ ] **Step 1: Write failing tests for evidence writing**

Add this to `tests/test_release_gate_harness.py`:

```python
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
```

- [ ] **Step 2: Run the tests and verify failure**

Run:

```powershell
python -m pytest tests/test_release_gate_harness.py -q
```

Expected: fail with `ModuleNotFoundError` for `scripts.release_gate.evidence`.

- [ ] **Step 3: Add `__init__.py`**

Create `scripts/release_gate/__init__.py`:

```python
"""Release-gate orchestration helpers."""
```

- [ ] **Step 4: Implement evidence primitives**

Create `scripts/release_gate/evidence.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StageResult:
    stage: str
    status: str
    duration_seconds: float
    command: str
    artifacts: list[str]
    notes: list[str]


class EvidenceStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, relative_path: str) -> Path:
        return self.root / relative_path

    def write_json(self, relative_path: str, payload: dict[str, Any]) -> Path:
        target = self.path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return target

    def write_text(self, relative_path: str, text: str) -> Path:
        target = self.path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def write_stage_result(self, result: StageResult) -> Path:
        return self.write_json(f"{result.stage}.json", asdict(result))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_dataset_manifest(dataset_dir: Path, *, git_commit: str) -> dict[str, Any]:
    dataset_dir = dataset_dir.resolve()
    stl_files = sorted(dataset_dir.glob("*.stl"), key=lambda item: item.name.lower())
    files = [
        {
            "name": item.name,
            "path": str(item),
            "size_bytes": item.stat().st_size,
            "sha256": sha256_file(item),
        }
        for item in stl_files
    ]
    return {
        "source_path": str(dataset_dir),
        "stl_count": len(files),
        "total_bytes": sum(item["size_bytes"] for item in files),
        "git_commit": git_commit,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
```

- [ ] **Step 5: Implement verdict rendering**

Create `scripts/release_gate/verdict.py`:

```python
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .evidence import EvidenceStore, StageResult


def render_release_gate_json(
    *,
    stage_results: list[StageResult],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    ship = all(result.status == "pass" for result in stage_results)
    return {
        "ship": ship,
        "metadata": metadata,
        "stages": [asdict(result) for result in stage_results],
    }


def render_verdict(
    *,
    stage_results: list[StageResult],
    metadata: dict[str, Any],
) -> str:
    ship = all(result.status == "pass" for result in stage_results)
    lines = [
        f"SHIP: {'yes' if ship else 'no'}",
        "",
        "# Release Gate Verdict",
        "",
        f"- Git commit: `{metadata.get('git_commit', 'unknown')}`",
        f"- Dataset: `{metadata.get('dataset_path', 'unknown')}`",
        f"- STL count: `{metadata.get('stl_count', 'unknown')}`",
        f"- PreForm URL: `{metadata.get('preform_url', 'unknown')}`",
        "",
        "| Stage | Status | Duration | Artifacts |",
        "| --- | --- | ---: | --- |",
    ]
    for result in stage_results:
        artifacts = ", ".join(f"`{item}`" for item in result.artifacts) or "-"
        lines.append(
            f"| {result.stage} | {result.status} | {result.duration_seconds:.2f}s | {artifacts} |"
        )
    notes = [
        f"- {result.stage}: {note}"
        for result in stage_results
        for note in result.notes
    ]
    if notes:
        lines.extend(["", "## Notes", "", *notes])
    return "\n".join(lines) + "\n"


def write_verdict(
    store: EvidenceStore,
    *,
    stage_results: list[StageResult],
    metadata: dict[str, Any],
) -> None:
    store.write_json(
        "release-gate.json",
        render_release_gate_json(stage_results=stage_results, metadata=metadata),
    )
    store.write_text(
        "verdict.md",
        render_verdict(stage_results=stage_results, metadata=metadata),
    )
```

- [ ] **Step 6: Run the tests and verify pass**

Run:

```powershell
python -m pytest tests/test_release_gate_harness.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add scripts/release_gate/__init__.py scripts/release_gate/evidence.py scripts/release_gate/verdict.py tests/test_release_gate_harness.py
git commit -m "Add release gate evidence primitives" -m "The hard gate needs stable JSON evidence and a readable verdict before stage orchestration can be built."
```

---

### Task 2: Add Environment And PreForm Probes

**Files:**
- Modify: `scripts/release_gate/evidence.py`
- Create: `scripts/release_gate/preform_probe.py`
- Create: `scripts/release_gate/stages.py`
- Modify: `tests/test_release_gate_harness.py`

- [ ] **Step 1: Add failing tests for dataset and virtual-device validation**

Append to `tests/test_release_gate_harness.py`:

```python
import pytest

from scripts.release_gate.preform_probe import is_virtual_device
from scripts.release_gate.stages import validate_dataset


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
```

- [ ] **Step 2: Run the tests and verify failure**

Run:

```powershell
python -m pytest tests/test_release_gate_harness.py -q
```

Expected: fail because `preform_probe.py` and `stages.py` do not exist.

- [ ] **Step 3: Implement PreForm probe helpers**

Create `scripts/release_gate/preform_probe.py`:

```python
from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


def read_json_url(url: str, *, timeout_seconds: float = 10.0) -> Any:
    with urlopen(url, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def probe_preform(preform_url: str) -> dict[str, Any]:
    base = preform_url.rstrip("/")
    probes: dict[str, Any] = {"base_url": base, "reachable": False}
    try:
        probes["devices"] = read_json_url(f"{base}/devices/")
        probes["reachable"] = True
    except (OSError, URLError, json.JSONDecodeError) as exc:
        probes["error"] = str(exc)
    return probes


def is_virtual_device(device: dict[str, Any]) -> bool:
    if bool(device.get("is_virtual")):
        return True
    haystack = " ".join(
        str(device.get(key, ""))
        for key in ("id", "device_id", "name", "device_name", "model", "status")
    ).lower()
    return "virtual" in haystack or "debug" in haystack
```

- [ ] **Step 4: Implement dataset validation and stage names**

Create `scripts/release_gate/stages.py`:

```python
from __future__ import annotations

from pathlib import Path


STAGE_ORDER = [
    "environment",
    "static",
    "backend",
    "browser-mocked",
    "browser-live-app",
    "live-preform-virtual",
    "packaged-runtime",
    "evidence-verdict",
]


def validate_dataset(dataset_dir: Path) -> Path:
    dataset_dir = dataset_dir.resolve()
    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset folder does not exist: {dataset_dir}")
    if not dataset_dir.is_dir():
        raise NotADirectoryError(f"Dataset path is not a directory: {dataset_dir}")
    if not list(dataset_dir.glob("*.stl")):
        raise ValueError(f"No .stl files found in dataset folder: {dataset_dir}")
    return dataset_dir
```

- [ ] **Step 5: Run tests and verify pass**

Run:

```powershell
python -m pytest tests/test_release_gate_harness.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add scripts/release_gate/preform_probe.py scripts/release_gate/stages.py tests/test_release_gate_harness.py
git commit -m "Add release gate environment probes" -m "The gate now has explicit dataset validation and virtual/debug PreForm target detection before orchestration starts."
```

---

### Task 3: Build The Python Harness CLI

**Files:**
- Create: `scripts/release_gate/run_release_gate.py`
- Modify: `scripts/release_gate/stages.py`
- Modify: `tests/test_release_gate_harness.py`
- Modify: `scripts/release_gate/run_release_gate.mjs`
- Modify: `package.json`

- [ ] **Step 1: Add tests for argument defaults and command planning**

Append to `tests/test_release_gate_harness.py`:

```python
from scripts.release_gate.run_release_gate import build_parser, default_evidence_dir
from scripts.release_gate.stages import build_stage_plan


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
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_release_gate_harness.py -q
```

Expected: fail because `run_release_gate.py` and `build_stage_plan` are missing.

- [ ] **Step 3: Implement stage command planning**

Replace `scripts/release_gate/stages.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


STAGE_ORDER = [
    "environment",
    "static",
    "backend",
    "browser-mocked",
    "browser-live-app",
    "live-preform-virtual",
    "packaged-runtime",
    "evidence-verdict",
]


@dataclass(frozen=True)
class StageCommand:
    name: str
    command: list[str]
    timeout_seconds: int
    env: dict[str, str] = field(default_factory=dict)
    log_name: str = ""


def validate_dataset(dataset_dir: Path) -> Path:
    dataset_dir = dataset_dir.resolve()
    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset folder does not exist: {dataset_dir}")
    if not dataset_dir.is_dir():
        raise NotADirectoryError(f"Dataset path is not a directory: {dataset_dir}")
    if not list(dataset_dir.glob("*.stl")):
        raise ValueError(f"No .stl files found in dataset folder: {dataset_dir}")
    return dataset_dir


def build_stage_plan(
    *,
    evidence_dir: Path,
    test_data_dir: Path,
    preform_url: str,
    headed: bool,
    skip_package_build: bool,
) -> list[StageCommand]:
    common_env = {
        "FORMFLOW_RELEASE_EVIDENCE_DIR": str(evidence_dir),
        "FORMFLOW_RELEASE_TEST_DATA_DIR": str(test_data_dir),
        "PREFORM_SERVER_URL": preform_url,
        "FORMFLOW_WEB_PRINT_DISPATCH_MODE": "virtual",
        "ANDENT_WEB_PRINT_DISPATCH_MODE": "virtual",
    }
    headed_flag = ["--headed"] if headed else []
    package_flag = ["--skip-package-build"] if skip_package_build else []
    return [
        StageCommand("environment", ["python", "-m", "scripts.release_gate.run_release_gate", "environment-only"], 120, common_env, "environment.log"),
        StageCommand("static", ["python", "-m", "py_compile", "app/main.py", "scripts/release_gate/run_release_gate.py"], 180, common_env, "python-compile.log"),
        StageCommand("backend", ["python", "-m", "pytest", "tests/", "-q"], 600, common_env, "pytest.log"),
        StageCommand("browser-mocked", ["npx", "playwright", "test", "tests/e2e", "tests/release_gate/smoke.spec.ts", "tests/release_gate/ui-hooks.spec.ts", "tests/release_gate/bulk-actions.spec.ts", "--project=chromium"], 300, common_env, "browser-mocked.log"),
        StageCommand("browser-live-app", ["npx", "playwright", "test", "tests/release_gate/live_virtual_handoff.spec.ts", "--project=chromium", *headed_flag], 480, common_env, "browser-live-app.log"),
        StageCommand("live-preform-virtual", ["npx", "playwright", "test", "tests/release_gate/live_pack_invariants.spec.ts", "--project=chromium", *headed_flag], 1200, common_env, "live-preform-virtual.log"),
        StageCommand("packaged-runtime", ["npx", "playwright", "test", "tests/release_gate/packaged_runtime.spec.ts", "--project=chromium", *headed_flag, *package_flag], 600, common_env, "packaged-runtime.log"),
    ]
```

- [ ] **Step 4: Implement CLI parser and environment-only mode**

Create `scripts/release_gate/run_release_gate.py`:

```python
from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import time

from .evidence import EvidenceStore, StageResult, build_dataset_manifest
from .preform_probe import probe_preform
from .stages import build_stage_plan, validate_dataset
from .verdict import write_verdict


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
    subprocess.run(["git", "status", "--short"], text=True, stdout=store.path("git-status.txt").open("w", encoding="utf-8"), check=False)
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
        import json
        metadata["stl_count"] = json.loads(dataset_manifest_path.read_text(encoding="utf-8")).get("stl_count")
    write_verdict(store, stage_results=results, metadata=metadata)
    return 0 if all(result.status == "pass" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Update Node wrapper**

Replace `scripts/release_gate/run_release_gate.mjs` with:

```javascript
import { spawn } from 'node:child_process';

const child = spawn(
  'python',
  ['scripts/release_gate/run_release_gate.py', ...process.argv.slice(2)],
  { stdio: 'inherit', shell: false },
);

child.on('exit', (code) => process.exit(code ?? 1));
```

- [ ] **Step 6: Update npm scripts**

Modify `package.json` scripts to include:

```json
{
  "scripts": {
    "test:release-gate": "python scripts/release_gate/run_release_gate.py",
    "test:release-gate:headed": "python scripts/release_gate/run_release_gate.py --headed",
    "test:release-gate:headed:live": "python scripts/release_gate/run_release_gate.py --headed"
  }
}
```

Keep existing dependency entries unchanged.

- [ ] **Step 7: Run harness unit tests**

Run:

```powershell
python -m pytest tests/test_release_gate_harness.py -q
```

Expected: pass.

- [ ] **Step 8: Run environment-only gate against canonical dataset**

Run:

```powershell
python scripts/release_gate/run_release_gate.py environment-only --test-data-dir "C:\Users\Marcus\Desktop\From 4BL Test Data"
```

Expected when PreFormServer is running: exit code `0`, evidence contains `dataset-manifest.json`, `preform-status.json`, `release-gate.json`, and `verdict.md`.

Expected when PreFormServer is not running: exit code `1`, `verdict.md` contains `SHIP: no`.

- [ ] **Step 9: Commit**

Run:

```powershell
git add scripts/release_gate/run_release_gate.py scripts/release_gate/stages.py scripts/release_gate/run_release_gate.mjs package.json tests/test_release_gate_harness.py
git commit -m "Add staged release gate harness" -m "The release command now validates the canonical dataset, probes PreFormServer, runs staged checks, and writes a ship/no-ship verdict."
```

---

### Task 4: Strengthen Playwright Runtime Helpers

**Files:**
- Modify: `tests/release_gate/helpers/runtime.ts`
- Modify: `tests/release_gate/helpers/page.ts`

- [ ] **Step 1: Add helper functions to `page.ts`**

Extend `tests/release_gate/helpers/page.ts` with:

```typescript
import path from 'node:path';
import { expect, type Page } from '@playwright/test';

export async function waitForRowReady(page: Page, fileName: string): Promise<void> {
  const row = page.locator(`[data-file-name="${fileName}"]`);
  await expect(row).toBeVisible();
  await expect(row.locator('[data-testid="status-chip"]')).toHaveText('Ready');
}

export async function uploadStlFolder(page: Page, folderPath: string): Promise<string[]> {
  const fs = await import('node:fs/promises');
  const entries = await fs.readdir(folderPath);
  const files = entries
    .filter((entry) => entry.toLowerCase().endsWith('.stl'))
    .sort((a, b) => a.localeCompare(b))
    .map((entry) => path.join(folderPath, entry));
  if (files.length === 0) {
    throw new Error(`No STL files found in ${folderPath}`);
  }
  await page.locator('#file-input').setInputFiles(files);
  return files.map((file) => path.basename(file));
}

export async function waitForClassificationToSettle(page: Page, expectedMinimumRows: number): Promise<void> {
  await expect(page.locator('[data-testid="status-chip"]').first()).toBeVisible({ timeout: 120_000 });
  await page.waitForFunction(
    ({ minimumRows }) => {
      const chips = Array.from(document.querySelectorAll('[data-testid="status-chip"]'));
      if (chips.length < minimumRows) return false;
      return chips.every((chip) => !/Processing|Analyzing/i.test((chip as HTMLElement).innerText));
    },
    { minimumRows: expectedMinimumRows },
    { timeout: 180_000 },
  );
}

export async function writeClassificationSummary(page: Page, outputPath: string): Promise<void> {
  const fs = await import('node:fs/promises');
  const statuses = await page.locator('[data-testid="status-chip"]').allTextContents();
  const counts = statuses.reduce<Record<string, number>>((acc, status) => {
    const key = status.trim() || 'Unknown';
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, JSON.stringify({ counts, total: statuses.length }, null, 2), 'utf8');
}
```

- [ ] **Step 2: Extend `runtime.ts` env support**

Modify `startAppInstance` in `tests/release_gate/helpers/runtime.ts` so callers can pass extra env:

```typescript
export async function startAppInstance(opts: {
  port: number;
  dataDir: string;
  preformUrl: string;
  extraEnv?: Record<string, string>;
}): Promise<AppInstance> {
  await fs.rm(opts.dataDir, { recursive: true, force: true });
  await fs.mkdir(opts.dataDir, { recursive: true });
  const databasePath = path.join(opts.dataDir, 'formflow.db');
  const child = spawn(
    'python',
    ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(opts.port)],
    {
      cwd: process.cwd(),
      env: {
        ...process.env,
        FORMFLOW_WEB_DATA_DIR: opts.dataDir,
        FORMFLOW_WEB_DATABASE_PATH: databasePath,
        FORMFLOW_WEB_APPDATA_DIR: path.join(opts.dataDir, 'appdata'),
        FORMFLOW_WEB_PRINT_HOLD_DENSITY_TARGET: '0.0',
        FORMFLOW_WEB_PRINT_DISPATCH_MODE: 'virtual',
        ANDENT_WEB_PRINT_DISPATCH_MODE: 'virtual',
        PREFORM_SERVER_URL: opts.preformUrl,
        ...(opts.extraEnv ?? {}),
      },
      stdio: 'pipe',
    },
  );

  const baseURL = `http://127.0.0.1:${opts.port}`;
  await waitForHealth(`${baseURL}/health`);

  return { baseURL, dataDir: opts.dataDir, databasePath, preformUrl: opts.preformUrl, process: child };
}
```

- [ ] **Step 3: Run TypeScript compile**

Run:

```powershell
npx tsc --noEmit
```

Expected: pass.

- [ ] **Step 4: Commit**

Run:

```powershell
git add tests/release_gate/helpers/page.ts tests/release_gate/helpers/runtime.ts
git commit -m "Add release gate browser helpers" -m "Playwright live stages now have shared upload, classification, and virtual-dispatch runtime helpers."
```

---

### Task 5: Add Live Browser Dataset Flow

**Files:**
- Create: `tests/release_gate/live_virtual_handoff.spec.ts`
- Modify: `tests/release_gate/helpers/fixtures.ts`
- Modify: `tests/release_gate/helpers/python/release_gate_verify.py`

- [ ] **Step 1: Extend Python verification helper for classification summaries**

Add a `queue-summary` command to `tests/release_gate/helpers/python/release_gate_verify.py`:

```python
def queue_summary(database_path: str) -> dict:
    import sqlite3
    with sqlite3.connect(database_path) as conn:
        rows = conn.execute(
            """SELECT status, queue_section, COUNT(*)
               FROM upload_rows
               GROUP BY status, queue_section
               ORDER BY status, queue_section"""
        ).fetchall()
    return {
        "rows": [
            {"status": status, "queue_section": section, "count": count}
            for status, section, count in rows
        ]
    }
```

Wire it into the existing CLI dispatcher:

```python
if args.command == "queue-summary":
    print(json.dumps(queue_summary(args.database_path)))
    return
```

If the helper currently uses subparsers, add `queue-summary` as a subcommand with `--database-path`.

- [ ] **Step 2: Extend Playwright fixtures**

In `tests/release_gate/helpers/fixtures.ts`, add this fixture type:

```typescript
queueSummary: (databasePath: string) => Promise<any>;
```

Add the fixture implementation:

```typescript
queueSummary: async ({}, use) => {
  await use((databasePath) => runVerify(['queue-summary', '--database-path', databasePath]));
},
```

- [ ] **Step 3: Add live browser dataset spec**

Create `tests/release_gate/live_virtual_handoff.spec.ts`:

```typescript
import path from 'node:path';
import { expect, test } from './helpers/fixtures.js';
import {
  uploadStlFolder,
  waitForClassificationToSettle,
  writeClassificationSummary,
} from './helpers/page.js';

test('canonical dataset uploads, classifies, and persists in live browser app', async ({ page, liveApp, queueSummary }) => {
  test.setTimeout(300_000);

  const datasetDir = process.env.FORMFLOW_RELEASE_TEST_DATA_DIR;
  const evidenceDir = process.env.FORMFLOW_RELEASE_EVIDENCE_DIR ?? 'test-results/release-gate';
  if (!datasetDir) {
    throw new Error('FORMFLOW_RELEASE_TEST_DATA_DIR must point at the canonical release dataset.');
  }

  await page.goto(liveApp.baseURL);
  await expect(page.getByRole('heading', { name: 'Active Queue' })).toBeVisible();

  const uploadedNames = await uploadStlFolder(page, datasetDir);
  await waitForClassificationToSettle(page, Math.min(uploadedNames.length, 1));
  await writeClassificationSummary(page, path.join(evidenceDir, 'classification-summary.json'));

  const summary = await queueSummary(liveApp.databasePath);
  const totalRows = summary.rows.reduce((total: number, row: any) => total + row.count, 0);
  expect(totalRows).toBe(uploadedNames.length);

  await page.reload({ waitUntil: 'networkidle' });
  await expect(page.locator('[data-testid="status-chip"]').first()).toBeVisible({ timeout: 30_000 });
});
```

- [ ] **Step 4: Run the new spec with canonical dataset**

Run:

```powershell
$env:FORMFLOW_RELEASE_TEST_DATA_DIR = "C:\Users\Marcus\Desktop\From 4BL Test Data"
$env:FORMFLOW_RELEASE_EVIDENCE_DIR = "test-results\release-gate\manual-live-browser"
npx playwright test tests/release_gate/live_virtual_handoff.spec.ts --project=chromium
```

Expected: pass when the app can classify all dataset files.

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/release_gate/live_virtual_handoff.spec.ts tests/release_gate/helpers/fixtures.ts tests/release_gate/helpers/python/release_gate_verify.py
git commit -m "Add canonical dataset browser gate" -m "The live browser stage now uploads the release dataset, waits for classification, and records durable queue evidence."
```

---

### Task 6: Add Live Virtual PreForm And Pack-Invariant Specs

**Files:**
- Create: `tests/release_gate/live_pack_invariants.spec.ts`
- Modify: `tests/release_gate/helpers/python/release_gate_verify.py`
- Modify: `tests/release_gate/helpers/fixtures.ts`

- [ ] **Step 1: Add DB evidence command**

Add this helper to `tests/release_gate/helpers/python/release_gate_verify.py`:

```python
def print_job_summary(database_path: str) -> dict:
    import json
    import sqlite3
    with sqlite3.connect(database_path) as conn:
        conn.row_factory = sqlite3.Row
        jobs = conn.execute(
            """SELECT id, job_name, status, hold_reason, printer_device_id,
                      printer_device_name, case_ids_json, preset_names_json,
                      compatibility_key, manifest_json, scene_id
               FROM print_jobs
               ORDER BY id"""
        ).fetchall()
    payload = []
    for row in jobs:
        manifest = json.loads(row["manifest_json"]) if row["manifest_json"] else {}
        payload.append({
            "id": row["id"],
            "job_name": row["job_name"],
            "status": row["status"],
            "hold_reason": row["hold_reason"],
            "printer_device_id": row["printer_device_id"],
            "printer_device_name": row["printer_device_name"],
            "case_ids": json.loads(row["case_ids_json"] or "[]"),
            "preset_names": json.loads(row["preset_names_json"] or "[]"),
            "compatibility_key": row["compatibility_key"],
            "manifest": manifest,
            "scene_id": row["scene_id"],
        })
    return {"jobs": payload}
```

Wire it into the CLI as `print-job-summary --database-path`.

- [ ] **Step 2: Add fixture wrapper**

In `tests/release_gate/helpers/fixtures.ts`, add:

```typescript
printJobSummary: (databasePath: string) => Promise<any>;
```

Add implementation:

```typescript
printJobSummary: async ({}, use) => {
  await use((databasePath) => runVerify(['print-job-summary', '--database-path', databasePath]));
},
```

- [ ] **Step 3: Add live pack invariant spec**

Create `tests/release_gate/live_pack_invariants.spec.ts`:

```typescript
import fs from 'node:fs/promises';
import path from 'node:path';
import { expect, test } from './helpers/fixtures.js';
import { uploadStlFolder, waitForClassificationToSettle } from './helpers/page.js';

test('canonical dataset virtual dispatch records manifests and avoids physical dispatch', async ({ page, liveApp, printJobSummary, sceneStatus }) => {
  test.setTimeout(600_000);

  const datasetDir = process.env.FORMFLOW_RELEASE_TEST_DATA_DIR;
  const evidenceDir = process.env.FORMFLOW_RELEASE_EVIDENCE_DIR ?? 'test-results/release-gate';
  if (!datasetDir) {
    throw new Error('FORMFLOW_RELEASE_TEST_DATA_DIR must point at the canonical release dataset.');
  }

  await page.goto(liveApp.baseURL);
  const uploadedNames = await uploadStlFolder(page, datasetDir);
  await waitForClassificationToSettle(page, Math.min(uploadedNames.length, 1));

  const readyRows = page.locator('#active-body tr').filter({
    has: page.locator('[data-testid="status-chip"]', { hasText: 'Ready' }),
  });
  const readyCount = await readyRows.count();
  expect(readyCount).toBeGreaterThan(0);

  await readyRows.first().locator('[data-testid="row-select"]').check();
  await expect(page.locator('[data-testid="send-to-print-button"]')).toBeEnabled({ timeout: 30_000 });
  await page.locator('[data-testid="send-to-print-button"]').click();
  await expect(page.locator('#status-text')).toContainText(/Moved|Submitted|Holding/i, { timeout: 180_000 });

  const summary = await printJobSummary(liveApp.databasePath);
  await fs.mkdir(evidenceDir, { recursive: true });
  await fs.writeFile(path.join(evidenceDir, 'print-job-evidence.json'), JSON.stringify(summary, null, 2), 'utf8');

  expect(summary.jobs.length).toBeGreaterThan(0);
  const physicalIndicators = summary.jobs.filter((job: any) => {
    const target = `${job.printer_device_id ?? ''} ${job.printer_device_name ?? ''}`.toLowerCase();
    return !target.includes('virtual') && !target.includes('debug');
  });
  expect(physicalIndicators).toEqual([]);

  const firstJobWithScene = summary.jobs.find((job: any) => job.scene_id);
  expect(firstJobWithScene).toBeTruthy();
  const scene = await sceneStatus(liveApp.preformUrl, firstJobWithScene.scene_id);
  await fs.writeFile(path.join(evidenceDir, 'preform-scene-evidence.json'), JSON.stringify(scene, null, 2), 'utf8');
  expect(scene.scene_id).toBe(firstJobWithScene.scene_id);

  const heldByCompatibility = new Map<string, number>();
  for (const job of summary.jobs) {
    if (job.status === 'Holding for More Cases') {
      heldByCompatibility.set(job.compatibility_key, (heldByCompatibility.get(job.compatibility_key) ?? 0) + 1);
    }
    expect(job.manifest.case_ids?.length ?? job.case_ids.length).toBeGreaterThan(0);
  }
  for (const count of heldByCompatibility.values()) {
    expect(count).toBeLessThanOrEqual(1);
  }

  await fs.writeFile(path.join(evidenceDir, 'no-physical-dispatch.json'), JSON.stringify({
    pass: physicalIndicators.length === 0,
    checked_jobs: summary.jobs.length,
  }, null, 2), 'utf8');
});
```

- [ ] **Step 4: Run live pack invariant spec**

Run:

```powershell
$env:FORMFLOW_RELEASE_TEST_DATA_DIR = "C:\Users\Marcus\Desktop\From 4BL Test Data"
$env:FORMFLOW_RELEASE_EVIDENCE_DIR = "test-results\release-gate\manual-live-preform"
npx playwright test tests/release_gate/live_pack_invariants.spec.ts --project=chromium --headed
```

Expected: pass with PreFormServer running and a virtual/debug target available.

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/release_gate/live_pack_invariants.spec.ts tests/release_gate/helpers/fixtures.ts tests/release_gate/helpers/python/release_gate_verify.py
git commit -m "Add live virtual PreForm release proof" -m "The gate now verifies manifest evidence, scene evidence, and no physical dispatch while using the canonical release dataset."
```

---

### Task 7: Add Packaged Runtime Stage

**Files:**
- Create: `tests/release_gate/packaged_runtime.spec.ts`
- Modify: `tests/release_gate/helpers/runtime.ts`
- Modify: `scripts/release_gate/stages.py`

- [ ] **Step 1: Add packaged runtime launcher helper**

Append to `tests/release_gate/helpers/runtime.ts`:

```typescript
export async function findPackagedExecutable(): Promise<string> {
  const candidates = [
    path.resolve('dist/FormFlow/FormFlow.exe'),
    path.resolve('dist/FormFlow.exe'),
  ];
  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      return candidate;
    } catch {}
  }
  throw new Error(`No packaged FormFlow executable found. Checked: ${candidates.join(', ')}`);
}
```

- [ ] **Step 2: Add packaged runtime spec**

Create `tests/release_gate/packaged_runtime.spec.ts`:

```typescript
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { expect, test } from '@playwright/test';
import { findPackagedExecutable } from './helpers/runtime.js';

async function waitForUrl(url: string, timeoutMs = 90_000): Promise<void> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

test('packaged runtime starts and serves browser app', async ({ page }) => {
  test.setTimeout(180_000);

  const evidenceDir = process.env.FORMFLOW_RELEASE_EVIDENCE_DIR ?? 'test-results/release-gate';
  const dataDir = path.resolve('test-results/release-gate/packaged-appdata');
  await fs.rm(dataDir, { recursive: true, force: true });
  await fs.mkdir(dataDir, { recursive: true });

  const exePath = await findPackagedExecutable();
  const child: ChildProcessWithoutNullStreams = spawn(exePath, [], {
    env: {
      ...process.env,
      FORMFLOW_WEB_OPEN_BROWSER: '0',
      FORMFLOW_WEB_APPDATA_DIR: dataDir,
      FORMFLOW_WEB_DATA_DIR: path.join(dataDir, 'data'),
      FORMFLOW_WEB_DATABASE_PATH: path.join(dataDir, 'formflow.db'),
      FORMFLOW_WEB_PRINT_DISPATCH_MODE: 'virtual',
      ANDENT_WEB_PRINT_DISPATCH_MODE: 'virtual',
    },
    stdio: 'pipe',
  });

  try {
    await waitForUrl('http://127.0.0.1:8090/health');
    await page.goto('http://127.0.0.1:8090/');
    await expect(page.getByRole('heading', { name: 'Active Queue' })).toBeVisible();
    await fs.mkdir(evidenceDir, { recursive: true });
    await fs.writeFile(path.join(evidenceDir, 'packaged-runtime.json'), JSON.stringify({
      exePath,
      health: 'ok',
      url: 'http://127.0.0.1:8090/',
    }, null, 2), 'utf8');
  } finally {
    child.kill();
  }
});
```

- [ ] **Step 3: Ensure stage builds package before Playwright unless skipped**

In `scripts/release_gate/stages.py`, change the packaged runtime command to call a Python wrapper script only if package build is required:

```python
packaged_command = (
    ["npx", "playwright", "test", "tests/release_gate/packaged_runtime.spec.ts", "--project=chromium", *headed_flag]
    if skip_package_build
    else ["python", "-m", "pytest", "tests/test_exe_packaging.py", "-q"]
)
```

Then add a separate `packaged-runtime-browser` stage only if needed, or keep the Playwright command and document that the user must run packaging first for the initial implementation. Prefer the separate stage only if `tests/test_exe_packaging.py` already creates `dist/FormFlow.exe` reliably.

- [ ] **Step 4: Run packaged spec**

Run:

```powershell
npx playwright test tests/release_gate/packaged_runtime.spec.ts --project=chromium
```

Expected: pass when a packaged executable exists in `dist/`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/release_gate/packaged_runtime.spec.ts tests/release_gate/helpers/runtime.ts scripts/release_gate/stages.py
git commit -m "Add packaged runtime release gate stage" -m "The ship gate now verifies the Windows runtime path serves the browser app with isolated release data."
```

---

### Task 8: Wire Final Evidence And Documentation

**Files:**
- Modify: `scripts/release_gate/run_release_gate.py`
- Modify: `README.md`
- Modify: `package.json`

- [ ] **Step 1: Ensure final verdict always writes after failures**

In `scripts/release_gate/run_release_gate.py`, replace `main()` with this version:

```python
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = EvidenceStore(args.evidence_dir)
    results: list[StageResult] = []
    metadata = {
        "git_commit": git_commit(),
        "dataset_path": str(args.test_data_dir),
        "preform_url": args.preform_url,
    }
    try:
        results.append(run_environment(args, store))
        dataset_manifest_path = store.path("dataset-manifest.json")
        if dataset_manifest_path.exists():
            import json
            metadata["stl_count"] = json.loads(
                dataset_manifest_path.read_text(encoding="utf-8")
            ).get("stl_count")
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
    except Exception as exc:
        results.append(
            StageResult("release-gate", "fail", 0.0, "internal", [], [str(exc)])
        )
    finally:
        write_verdict(store, stage_results=results, metadata=metadata)
    return 0 if results and all(result.status == "pass" for result in results) else 1
```

- [ ] **Step 2: Add README release-gate section**

Update `README.md` Release Gate section to:

````markdown
## Hard Release Gate

The ship/no-ship gate requires a live PreFormServer at `http://127.0.0.1:44388` and the canonical dataset at:

```text
C:\Users\Marcus\Desktop\From 4BL Test Data
```

Run:

```powershell
python scripts/release_gate/run_release_gate.py `
  --test-data-dir "C:\Users\Marcus\Desktop\From 4BL Test Data" `
  --preform-url "http://127.0.0.1:44388"
```

The gate writes evidence under `docs/02_planning/98_VerificationArtifacts/pre_release_*`.
A release is green only when `verdict.md` contains `SHIP: yes`.
The gate uses virtual/debug PreForm dispatch only and fails if physical dispatch is selected or used.
````

- [ ] **Step 3: Run final fast verification**

Run:

```powershell
python -m pytest tests/test_release_gate_harness.py -q
npx tsc --noEmit
python scripts/release_gate/run_release_gate.py environment-only --test-data-dir "C:\Users\Marcus\Desktop\From 4BL Test Data"
```

Expected: harness tests pass, TypeScript compiles, environment-only gate writes evidence. If PreFormServer is not running, environment-only should produce `SHIP: no`; start PreFormServer and rerun before claiming release-gate completion.

- [ ] **Step 4: Run full hard gate**

Run with live PreFormServer already running:

```powershell
python scripts/release_gate/run_release_gate.py `
  --test-data-dir "C:\Users\Marcus\Desktop\From 4BL Test Data" `
  --preform-url "http://127.0.0.1:44388" `
  --headed
```

Expected: exit code `0`; latest `verdict.md` contains `SHIP: yes`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add scripts/release_gate/run_release_gate.py README.md package.json
git commit -m "Document and finalize the hard release gate" -m "The release process now has one documented ship/no-ship command with durable evidence and a virtual PreForm dispatch boundary."
```

---

## Verification Checklist

Before reporting implementation complete:

- [ ] `python -m pytest tests/test_release_gate_harness.py -q` passes.
- [ ] `python -m pytest tests/ -q` passes, or failures are fixed before continuing.
- [ ] `npx tsc --noEmit` passes.
- [ ] `npx playwright test tests/e2e tests/release_gate/smoke.spec.ts tests/release_gate/ui-hooks.spec.ts tests/release_gate/bulk-actions.spec.ts --project=chromium` passes.
- [ ] Live PreFormServer is reachable at `http://127.0.0.1:44388`.
- [ ] `python scripts/release_gate/run_release_gate.py --test-data-dir "C:\Users\Marcus\Desktop\From 4BL Test Data" --preform-url "http://127.0.0.1:44388"` exits `0`.
- [ ] Latest `verdict.md` says `SHIP: yes`.
- [ ] Latest `dataset-manifest.json` records the canonical dataset path and STL files.
- [ ] Latest `no-physical-dispatch.json` passes.
- [ ] Latest `print-job-evidence.json` includes manifests and virtual/debug target evidence.
- [ ] Packaged runtime stage passes or the release is blocked.

## Known Implementation Risks

- The 91-file browser upload may exceed the current 8-minute live-browser timeout. If it does, raise the timeout in `build_stage_plan()` and record the measured runtime in `verdict.md`.
- The virtual/debug device naming may differ across PreFormServer versions. If `is_virtual_device()` rejects a valid virtual device, extend it with a recorded metadata key rather than weakening the physical-dispatch guard.
- `tests/test_exe_packaging.py` may not produce the final executable path expected by `findPackagedExecutable()`. If paths differ, update `findPackagedExecutable()` with the actual dist path and keep both old and new candidates.
- Existing unrelated worktree changes must not be reverted while executing this plan.

---

## 2026-05-05 Continuation Log

Implemented and committed release-gate foundations through packaged runtime proof:

- `3d6cf8d` - evidence primitives and verdict rendering.
- `73c9db7` - canonical dataset validation and PreForm virtual/debug device probes.
- `5329e68` - staged Python release-gate harness and Node compatibility wrapper.
- `4350cd0` - browser helpers for real STL folder upload and isolated app startup.
- `470426c` - canonical dataset browser classification gate.
- `b7a425a` - live virtual PreForm dispatch proof and no-physical-dispatch evidence.
- `f3e9c98` - packaged EXE startup proof against `dist\FormFlow_v0.1.0.exe`.

Additional final-wiring changes pending in the next commit:

- `run_release_gate.py` now records a no-ship harness stage on unexpected exceptions and writes verdict evidence instead of dropping a raw stack trace.
- `stages.py` disables third-party pytest plugin autoload for backend tests, resolves `npx.cmd` on Windows, limits virtual dispatch env to the live browser/PreForm stages, and runs the mocked browser stage serially with a longer timeout.
- `tests/test_release_gate_harness.py` covers those stage-planning guardrails.
- `README.md` documents the hard ship/no-ship release gate, prerequisites, and evidence location.

Verification captured before pausing:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_release_gate_harness.py -q` -> 16 passed.
- `python -m py_compile scripts\release_gate\run_release_gate.py scripts\release_gate\stages.py tests\test_release_gate_harness.py` -> passed.
- `npx tsc --noEmit` -> passed.
- Focused packaged runtime Playwright proof passed and wrote `test-results\release-gate\manual-packaged-runtime\packaged-runtime.json`.
- Full hard gate reached backend successfully after fixes: backend stage logged `455 passed, 3 skipped`.

Current no-ship blocker:

- The existing mocked browser/E2E stage is not green. Serial focused run of `npx.cmd playwright test tests/e2e tests/release_gate/smoke.spec.ts tests/release_gate/ui-hooks.spec.ts tests/release_gate/bulk-actions.spec.ts --project=chromium --workers=1` produced 23 failures and 1 pass.
- Primary failure groups: stale row-selection expectations, stale legend/status-chip expectations, preview/undo/bulk tests failing after the app server became unavailable.
- The interrupted final full-gate run was stopped intentionally by the user; its spawned release-gate, Playwright, and port-8200 uvicorn child processes were terminated before this log was written.

Next continuation target:

1. Fix or retire stale mocked browser specs so the browser-mocked stage is a meaningful production gate.
2. Re-run the full hard gate against `C:\Users\Marcus\Desktop\From 4BL Test Data` and live PreFormServer at `http://127.0.0.1:44388`.
3. Treat release as blocked until the final generated `verdict.md` says `SHIP: yes`.
