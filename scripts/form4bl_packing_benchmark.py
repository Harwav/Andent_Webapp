from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.build_planning import plan_build_manifests
from app.services.classification import classify_saved_upload
from app.services.preform_client import PreFormClient


def load_rows(folder: Path) -> list:
    if not folder.exists():
        raise FileNotFoundError(f"Benchmark folder does not exist: {folder}")
    rows = []
    for idx, path in enumerate(sorted(folder.glob("*.stl")), start=1):
        row = classify_saved_upload(path, path.name)
        row.row_id = idx
        row.file_path = str(path)
        rows.append(row)
    if not rows:
        raise ValueError(f"Benchmark folder contains no STL files: {folder}")
    return rows


def planner_summary(rows: list) -> dict[str, object]:
    manifests = plan_build_manifests(rows)
    planned = [manifest for manifest in manifests if manifest.planning_status == "planned"]
    return {
        "total_files": len(rows),
        "manifest_count": len(manifests),
        "planned_manifest_count": len(planned),
        "average_cases_per_build": round(
            sum(len(manifest.case_ids) for manifest in planned) / len(planned),
            2,
        ) if planned else 0.0,
        "average_models_per_build": round(
            sum(
                sum(len(group.files) for group in manifest.import_groups)
                for manifest in planned
            ) / len(planned),
            2,
        ) if planned else 0.0,
        "planned_case_counts": [len(manifest.case_ids) for manifest in planned],
        "planned_model_counts": [
            sum(len(group.files) for group in manifest.import_groups)
            for manifest in planned
        ],
    }


def _manifest_model_count(manifest) -> int:
    return sum(len(group.files) for group in manifest.import_groups)


def live_validation_summary(rows: list, preform_url: str) -> dict[str, object]:
    manifests = [
        manifest
        for manifest in plan_build_manifests(rows)
        if manifest.planning_status == "planned"
    ]
    results = []
    client = PreFormClient(preform_url)
    try:
        for index, manifest in enumerate(manifests, start=1):
            started_at = time.perf_counter()
            scene_id = None
            errors: list[str] = []
            try:
                scene = client.create_scene(
                    patient_id=manifest.case_ids[0],
                    case_name=f"full-arch-calibration-{index:03d}",
                )
                scene_id = scene.get("scene_id")
                if not scene_id:
                    raise RuntimeError("PreFormServer did not return a scene_id")

                for group in manifest.import_groups:
                    for file_spec in group.files:
                        client.import_model(
                            scene_id,
                            file_spec.file_path,
                            preset=file_spec.preform_hint,
                        )

                client.auto_layout(scene_id)
                validation = client.validate_scene(scene_id)
                validation_passed = bool(validation.get("valid", False))
                raw_errors = validation.get("errors", [])
                if isinstance(raw_errors, list):
                    errors = [str(error) for error in raw_errors]
                elif raw_errors:
                    errors = [str(raw_errors)]
            except Exception as exc:
                validation_passed = False
                errors = [str(exc)]

            results.append(
                {
                    "manifest_index": index,
                    "scene_id": scene_id,
                    "case_ids": manifest.case_ids,
                    "model_count": _manifest_model_count(manifest),
                    "validation_passed": validation_passed,
                    "errors": errors,
                    "processing_time_seconds": round(time.perf_counter() - started_at, 3),
                }
            )
    finally:
        client.close()

    successful = [result for result in results if result["validation_passed"]]
    return {
        "preform_url": preform_url,
        "planned_builds": len(manifests),
        "successful_builds": len(successful),
        "failed_builds": len(results) - len(successful),
        "average_models_per_build": round(
            sum(result["model_count"] for result in successful) / len(successful),
            2,
        ) if successful else 0.0,
        "average_processing_time_seconds": round(
            sum(result["processing_time_seconds"] for result in results) / len(results),
            3,
        ) if results else 0.0,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--live-output-json", type=Path)
    parser.add_argument("--preform-url", default="http://127.0.0.1:44388")
    args = parser.parse_args()

    rows = load_rows(args.folder)
    summary = planner_summary(rows)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if args.live_output_json is not None:
        live_summary = live_validation_summary(rows, args.preform_url)
        args.live_output_json.parent.mkdir(parents=True, exist_ok=True)
        args.live_output_json.write_text(
            json.dumps(live_summary, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(live_summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
