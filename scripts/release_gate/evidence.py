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
