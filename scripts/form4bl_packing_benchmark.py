from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.build_planning import plan_build_manifests
from app.services.classification import classify_saved_upload


def load_rows(folder: Path) -> list:
    rows = []
    for idx, path in enumerate(sorted(folder.glob("*.stl")), start=1):
        row = classify_saved_upload(path, path.name)
        row.row_id = idx
        row.file_path = str(path)
        rows.append(row)
    return rows


def planner_summary(rows: list) -> dict[str, object]:
    manifests = plan_build_manifests(rows)
    planned = [manifest for manifest in manifests if manifest.planning_status == "planned"]
    return {
        "total_files": len(rows),
        "manifest_count": len(manifests),
        "planned_manifest_count": len(planned),
        "planned_case_counts": [len(manifest.case_ids) for manifest in planned],
        "planned_model_counts": [
            sum(len(group.files) for group in manifest.import_groups)
            for manifest in planned
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()

    rows = load_rows(args.folder)
    summary = planner_summary(rows)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
