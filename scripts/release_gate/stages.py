from __future__ import annotations

from dataclasses import dataclass, field
import os
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


def command_name(name: str) -> str:
    if os.name == "nt" and name in {"npx", "npm"}:
        return f"{name}.cmd"
    return name


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
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    if skip_package_build:
        common_env["FORMFLOW_RELEASE_SKIP_PACKAGE_BUILD"] = "1"
    virtual_dispatch_env = {
        **common_env,
        "FORMFLOW_WEB_PRINT_DISPATCH_MODE": "virtual",
        "ANDENT_WEB_PRINT_DISPATCH_MODE": "virtual",
    }
    headed_flag = ["--headed"] if headed else []
    npx = command_name("npx")
    return [
        StageCommand(
            "environment",
            ["python", "-m", "scripts.release_gate.run_release_gate", "environment-only"],
            120,
            common_env,
            "environment.log",
        ),
        StageCommand(
            "static",
            ["python", "-m", "py_compile", "app/main.py", "scripts/release_gate/run_release_gate.py"],
            180,
            common_env,
            "python-compile.log",
        ),
        StageCommand(
            "backend",
            ["python", "-m", "pytest", "tests/", "-q"],
            600,
            common_env,
            "pytest.log",
        ),
        StageCommand(
            "browser-mocked",
            [
                npx,
                "playwright",
                "test",
                "tests/e2e",
                "tests/release_gate/smoke.spec.ts",
                "tests/release_gate/ui-hooks.spec.ts",
                "tests/release_gate/bulk-actions.spec.ts",
                "--project=chromium",
                "--workers=1",
            ],
            1200,
            common_env,
            "browser-mocked.log",
        ),
        StageCommand(
            "browser-live-app",
            [
                npx,
                "playwright",
                "test",
                "tests/release_gate/live_virtual_handoff.spec.ts",
                "--project=chromium",
                *headed_flag,
            ],
            480,
            virtual_dispatch_env,
            "browser-live-app.log",
        ),
        StageCommand(
            "live-preform-virtual",
            [
                npx,
                "playwright",
                "test",
                "tests/release_gate/live_pack_invariants.spec.ts",
                "--project=chromium",
                *headed_flag,
            ],
            1200,
            virtual_dispatch_env,
            "live-preform-virtual.log",
        ),
        StageCommand(
            "packaged-runtime",
            [
                npx,
                "playwright",
                "test",
                "tests/release_gate/packaged_runtime.spec.ts",
                "--project=chromium",
                *headed_flag,
            ],
            600,
            virtual_dispatch_env,
            "packaged-runtime.log",
        ),
    ]
