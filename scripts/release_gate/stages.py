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
