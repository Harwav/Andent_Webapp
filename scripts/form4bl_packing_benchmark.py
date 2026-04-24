from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import requests
from stl import mesh

from app.services.build_planning import plan_build_manifests
from app.services.classification import classify_saved_upload
from app.services.preform_client import PreFormClient


FORM4BL_PLATFORM_X_MM = 353.0
FORM4BL_PLATFORM_Y_MM = 196.0
FORM4BL_PLATFORM_AREA_MM2 = FORM4BL_PLATFORM_X_MM * FORM4BL_PLATFORM_Y_MM
MESH_RASTER_GRID_MM = 0.25
SCENE_SETTINGS = {
    "layer_thickness_mm": 0.1,
    "machine_type": "FRML-4-0",
    "material_code": "FLPMBE01",
    "print_setting": "DEFAULT",
}
SCAN_PARAMS = {
    "units": "DETECTED",
    "cutoff_height_mm": 0,
    "extrude_distance_mm": 0,
    "hollow": False,
}
LAYOUT_PARAMS = {
    "models": "ALL",
    "mode": "DENTAL",
    "model_spacing_mm": 0,
    "allow_overlapping_supports": False,
}
SCREENSHOT_PARAMS = {
    "view_type": "ZOOM_ON_MODELS",
    "crop_to_models": True,
    "image_size_px": 820,
}
ASYNC_TIMEOUT_SECONDS = 900.0


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


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: float = 60.0,
    **kwargs: Any,
) -> dict[str, Any]:
    response = session.request(method, url, timeout=timeout, **kwargs)
    response.raise_for_status()
    if not response.content:
        return {}
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object from {url}, got {type(payload).__name__}")
    return payload


def _poll_operation(
    session: requests.Session,
    preform_url: str,
    operation_id: str,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    last_status = ""
    while time.perf_counter() - started_at < ASYNC_TIMEOUT_SECONDS:
        payload = _request_json(
            session,
            "GET",
            f"{preform_url}/operations/{operation_id}/",
            timeout=30.0,
        )
        status = str(payload.get("status", "")).upper()
        if status and status != last_status:
            last_status = status
        if status in {"SUCCEEDED", "COMPLETED", "DONE", "SUCCESS"}:
            result = payload.get("result", {})
            return result if isinstance(result, dict) else {"result": result}
        if status in {"FAILED", "CANCELLED", "CANCELED", "ABORTED"}:
            raise RuntimeError(f"Operation {operation_id} ended with {status}: {payload}")
        elapsed = time.perf_counter() - started_at
        if elapsed < 5:
            time.sleep(0.1)
        elif elapsed < 30:
            time.sleep(0.5)
        else:
            time.sleep(1.0)
    raise TimeoutError(f"Operation {operation_id} timed out after {ASYNC_TIMEOUT_SECONDS}s")


def _async_request(
    session: requests.Session,
    preform_url: str,
    method: str,
    endpoint: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:
    response_payload = _request_json(
        session,
        method,
        f"{preform_url}/{endpoint.strip('/')}/",
        params={"async": "true"},
        json=payload,
        timeout=timeout,
    )
    operation_id = response_payload.get("operationId")
    if not operation_id:
        return response_payload
    return _poll_operation(session, preform_url, str(operation_id))


def _create_scene(session: requests.Session, preform_url: str) -> dict[str, Any]:
    scene = _request_json(
        session,
        "POST",
        f"{preform_url}/scene/",
        json=SCENE_SETTINGS,
        timeout=30.0,
    )
    scene_id = scene.get("id") or scene.get("scene_id")
    if not scene_id:
        raise RuntimeError(f"PreFormServer did not return a scene id: {scene}")
    return {**scene, "scene_id": str(scene_id)}


def _get_scene(session: requests.Session, preform_url: str, scene_id: str) -> dict[str, Any]:
    return _request_json(
        session,
        "GET",
        f"{preform_url}/scene/{scene_id}/",
        timeout=60.0,
    )


def _raw_validation_errors(payload: dict[str, Any]) -> list[str]:
    if "valid" in payload and "errors" in payload:
        raw_errors = payload.get("errors")
        if isinstance(raw_errors, list):
            return [str(error) for error in raw_errors]
        return [str(raw_errors)] if raw_errors else []

    errors: list[str] = []
    per_model_results = payload.get("per_model_results", {})
    if not isinstance(per_model_results, dict):
        return errors
    for model_id, result in per_model_results.items():
        if not isinstance(result, dict):
            continue
        if result.get("undersupported"):
            errors.append(f"{model_id}: undersupported")
        unsupported_minima = result.get("unsupported_minima", 0)
        if isinstance(unsupported_minima, (int, float)) and unsupported_minima:
            errors.append(f"{model_id}: unsupported minima {unsupported_minima}")
        cups = result.get("cups", 0)
        if isinstance(cups, (int, float)) and cups:
            errors.append(f"{model_id}: cups {cups}")
        if result.get("has_seamline"):
            errors.append(f"{model_id}: seamline detected")
    return errors


def _safe_build_stem(index: int, case_count: int, model_count: int) -> str:
    return f"form4bl_calibrated_build_{index:02d}_{case_count}cases_{model_count}models"


def export_form4bl_builds(
    rows: list,
    preform_url: str,
    output_folder: Path,
) -> dict[str, Any]:
    manifests = [
        manifest
        for manifest in plan_build_manifests(rows)
        if manifest.planning_status == "planned"
    ]
    output_folder.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    started_at = time.perf_counter()
    results: list[dict[str, Any]] = []
    try:
        for index, manifest in enumerate(manifests, start=1):
            build_started_at = time.perf_counter()
            expected_model_count = _manifest_model_count(manifest)
            stem = _safe_build_stem(index, len(manifest.case_ids), expected_model_count)
            form_path = output_folder / f"{stem}.form"
            screenshot_path = output_folder / f"{stem}.png"
            stage_seconds: dict[str, float] = {}
            errors: list[str] = []
            scene_id: str | None = None
            imported_model_count = 0
            layout_succeeded = False
            validation: dict[str, Any] | None = None
            scene_info: dict[str, Any] | None = None
            saved_form: str | None = None
            saved_screenshot: str | None = None

            try:
                stage_started = time.perf_counter()
                scene = _create_scene(session, preform_url)
                scene_id = scene["scene_id"]
                stage_seconds["create_scene"] = round(time.perf_counter() - stage_started, 3)

                stage_started = time.perf_counter()
                for group in manifest.import_groups:
                    for file_spec in group.files:
                        payload = {
                            "file": str(Path(file_spec.file_path).resolve()),
                            **SCAN_PARAMS,
                        }
                        _async_request(
                            session,
                            preform_url,
                            "POST",
                            f"scene/{scene_id}/scan-to-model/",
                            payload,
                            timeout=60.0,
                        )
                        imported_model_count += 1
                stage_seconds["import_models"] = round(time.perf_counter() - stage_started, 3)

                stage_started = time.perf_counter()
                _async_request(
                    session,
                    preform_url,
                    "POST",
                    f"scene/{scene_id}/auto-layout/",
                    dict(LAYOUT_PARAMS),
                    timeout=60.0,
                )
                layout_succeeded = True
                stage_seconds["auto_layout"] = round(time.perf_counter() - stage_started, 3)

                stage_started = time.perf_counter()
                scene_info = _get_scene(session, preform_url, scene_id)
                stage_seconds["scene_info"] = round(time.perf_counter() - stage_started, 3)

                stage_started = time.perf_counter()
                validation_payload = _async_request(
                    session,
                    preform_url,
                    "GET",
                    f"scene/{scene_id}/print-validation/",
                    timeout=60.0,
                )
                validation = {
                    "valid": not _raw_validation_errors(validation_payload),
                    "errors": _raw_validation_errors(validation_payload),
                    "raw": validation_payload,
                }
                stage_seconds["print_validation"] = round(time.perf_counter() - stage_started, 3)

                if imported_model_count != expected_model_count:
                    raise RuntimeError(
                        f"Imported {imported_model_count} models, expected {expected_model_count}"
                    )

                stage_started = time.perf_counter()
                _async_request(
                    session,
                    preform_url,
                    "POST",
                    f"scene/{scene_id}/save-form/",
                    {"file": str(form_path.resolve())},
                    timeout=60.0,
                )
                saved_form = str(form_path.resolve())
                stage_seconds["save_form"] = round(time.perf_counter() - stage_started, 3)

                stage_started = time.perf_counter()
                _async_request(
                    session,
                    preform_url,
                    "POST",
                    f"scene/{scene_id}/save-screenshot/",
                    {"file": str(screenshot_path.resolve()), **SCREENSHOT_PARAMS},
                    timeout=60.0,
                )
                saved_screenshot = str(screenshot_path.resolve())
                stage_seconds["save_screenshot"] = round(
                    time.perf_counter() - stage_started,
                    3,
                )
            except Exception as exc:
                errors.append(str(exc))

            results.append(
                {
                    "manifest_index": index,
                    "case_ids": manifest.case_ids,
                    "expected_model_count": expected_model_count,
                    "scene_id": scene_id,
                    "imported_model_count": imported_model_count,
                    "layout_succeeded": layout_succeeded,
                    "saved_form": saved_form,
                    "saved_screenshot": saved_screenshot,
                    "validation": validation,
                    "errors": errors,
                    "stage_seconds": stage_seconds,
                    "processing_time_seconds": round(
                        time.perf_counter() - build_started_at,
                        3,
                    ),
                    "scene": scene_info,
                }
            )
    finally:
        session.close()

    saved_builds = [
        result
        for result in results
        if result["saved_form"] and result["saved_screenshot"] and not result["errors"]
    ]
    summary = {
        "source_folder": str(Path(rows[0].file_path).parent) if rows else None,
        "output_folder": str(output_folder.resolve()),
        "preform_url": preform_url,
        "scene_settings": SCENE_SETTINGS,
        "scan_params": SCAN_PARAMS,
        "layout_params": LAYOUT_PARAMS,
        "screenshot_params": SCREENSHOT_PARAMS,
        "planned_builds": len(manifests),
        "saved_builds": len(saved_builds),
        "failed_builds": len(results) - len(saved_builds),
        "total_models": sum(result["expected_model_count"] for result in results),
        "average_models_per_saved_build": round(
            sum(result["expected_model_count"] for result in saved_builds) / len(saved_builds),
            2,
        ) if saved_builds else 0.0,
        "average_processing_time_seconds": round(
            sum(result["processing_time_seconds"] for result in results) / len(results),
            3,
        ) if results else 0.0,
        "total_processing_time_seconds": round(time.perf_counter() - started_at, 3),
        "results": results,
    }
    summary_path = output_folder / "export-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _point(model: dict[str, Any], key: str) -> np.ndarray:
    point = model["bounding_box"][key]
    return np.array([float(point["x"]), float(point["y"]), float(point["z"])])


def _transformed_vertices(model: dict[str, Any]) -> np.ndarray:
    stl_path = Path(str(model["original_file"]))
    stl_mesh = mesh.Mesh.from_file(str(stl_path))
    vertices = stl_mesh.vectors.reshape(-1, 3).astype(float)
    scale = float(model.get("scale", 1.0) or 1.0)
    vertices *= scale
    angle = math.radians(float(model.get("orientation", {}).get("z", 0.0) or 0.0))
    rotation = np.array(
        [
            [math.cos(angle), -math.sin(angle), 0.0],
            [math.sin(angle), math.cos(angle), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    position = model.get("position", {})
    translation = np.array(
        [
            float(position.get("x", 0.0) or 0.0),
            float(position.get("y", 0.0) or 0.0),
            float(position.get("z", 0.0) or 0.0),
        ]
    )
    return vertices @ rotation.T + translation


def _rasterize_scene_models(
    transformed_by_model: list[tuple[dict[str, Any], np.ndarray]],
    grid_mm: float,
) -> tuple[float, list[dict[str, Any]]]:
    if not transformed_by_model:
        return 0.0, []

    all_xy = np.vstack([vertices[:, :2] for _, vertices in transformed_by_model])
    build_min = np.floor(all_xy.min(axis=0) / grid_mm) * grid_mm - grid_mm
    build_max = np.ceil(all_xy.max(axis=0) / grid_mm) * grid_mm + grid_mm
    width = int(math.ceil((build_max[0] - build_min[0]) / grid_mm)) + 1
    height = int(math.ceil((build_max[1] - build_min[1]) / grid_mm)) + 1
    union = np.zeros((height, width), dtype=bool)
    model_summaries: list[dict[str, Any]] = []

    for model, vertices in transformed_by_model:
        xy = vertices[:, :2]
        model_min = np.floor(xy.min(axis=0) / grid_mm) * grid_mm - grid_mm
        model_max = np.ceil(xy.max(axis=0) / grid_mm) * grid_mm + grid_mm
        start_x = max(0, int(math.floor((model_min[0] - build_min[0]) / grid_mm)))
        start_y = max(0, int(math.floor((model_min[1] - build_min[1]) / grid_mm)))
        end_x = min(width, int(math.ceil((model_max[0] - build_min[0]) / grid_mm)) + 1)
        end_y = min(height, int(math.ceil((model_max[1] - build_min[1]) / grid_mm)) + 1)
        model_mask = np.zeros((end_y - start_y, end_x - start_x), dtype=bool)
        indices = np.floor((xy - build_min) / grid_mm).astype(int)
        local_x = indices[:, 0] - start_x
        local_y = indices[:, 1] - start_y
        valid = (
            (local_x >= 0)
            & (local_x < model_mask.shape[1])
            & (local_y >= 0)
            & (local_y < model_mask.shape[0])
        )
        model_mask[local_y[valid], local_x[valid]] = True
        model_mask = _binary_close_3x3(model_mask)
        model_mask = _binary_fill_holes(model_mask)
        model_mask = _binary_open_3x3(model_mask)
        union[start_y:end_y, start_x:end_x] |= model_mask
        model_summaries.append(
            {
                "model_id": model.get("id"),
                "name": model.get("name"),
                "original_file": model.get("original_file"),
                "mesh_projection_area_mm2": round(float(model_mask.sum()) * grid_mm * grid_mm, 3),
            }
        )

    union_area_mm2 = float(union.sum()) * grid_mm * grid_mm
    return union_area_mm2, model_summaries


def _binary_dilate_3x3(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask, 1, constant_values=False)
    result = np.zeros_like(mask, dtype=bool)
    for y_offset in range(3):
        for x_offset in range(3):
            result |= padded[y_offset:y_offset + mask.shape[0], x_offset:x_offset + mask.shape[1]]
    return result


def _binary_erode_3x3(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask, 1, constant_values=False)
    result = np.ones_like(mask, dtype=bool)
    for y_offset in range(3):
        for x_offset in range(3):
            result &= padded[y_offset:y_offset + mask.shape[0], x_offset:x_offset + mask.shape[1]]
    return result


def _binary_close_3x3(mask: np.ndarray) -> np.ndarray:
    return _binary_erode_3x3(_binary_dilate_3x3(mask))


def _binary_open_3x3(mask: np.ndarray) -> np.ndarray:
    return _binary_dilate_3x3(_binary_erode_3x3(mask))


def _binary_fill_holes(mask: np.ndarray) -> np.ndarray:
    if mask.size == 0:
        return mask
    background = ~mask
    reachable = np.zeros_like(mask, dtype=bool)
    frontier = np.zeros_like(mask, dtype=bool)
    frontier[0, :] |= background[0, :]
    frontier[-1, :] |= background[-1, :]
    frontier[:, 0] |= background[:, 0]
    frontier[:, -1] |= background[:, -1]

    while True:
        expanded = _binary_dilate_3x3(frontier) & background & ~reachable
        new_reachable = reachable | frontier
        if not expanded.any():
            reachable = new_reachable
            break
        reachable = new_reachable
        frontier = expanded

    holes = background & ~reachable
    return mask | holes


def _scene_density(scene: dict[str, Any], grid_mm: float) -> dict[str, Any]:
    models = scene.get("models", [])
    if not isinstance(models, list):
        models = []

    transformed_by_model: list[tuple[dict[str, Any], np.ndarray]] = []
    transform_errors: list[float] = []
    summed_bbox_area = 0.0
    missing_original_files: list[str] = []
    for model in models:
        if not isinstance(model, dict):
            continue
        original_file = model.get("original_file")
        if not original_file or not Path(str(original_file)).exists():
            missing_original_files.append(str(original_file))
            continue
        vertices = _transformed_vertices(model)
        transformed_by_model.append((model, vertices))
        transformed_min = vertices.min(axis=0)
        transformed_max = vertices.max(axis=0)
        bbox_min = _point(model, "min_corner")
        bbox_max = _point(model, "max_corner")
        transform_errors.append(
            float(max(np.max(np.abs(transformed_min - bbox_min)), np.max(np.abs(transformed_max - bbox_max))))
        )
        summed_bbox_area += max(0.0, bbox_max[0] - bbox_min[0]) * max(0.0, bbox_max[1] - bbox_min[1])

    union_area_mm2, model_summaries = _rasterize_scene_models(transformed_by_model, grid_mm)
    return {
        "model_count": len(models),
        "measured_model_count": len(transformed_by_model),
        "missing_original_files": missing_original_files,
        "mesh_projection_union_area_mm2": round(union_area_mm2, 3),
        "mesh_projection_density_pct": round(
            union_area_mm2 / FORM4BL_PLATFORM_AREA_MM2 * 100.0,
            2,
        ),
        "summed_bbox_area_mm2": round(summed_bbox_area, 3),
        "summed_bbox_density_pct": round(
            summed_bbox_area / FORM4BL_PLATFORM_AREA_MM2 * 100.0,
            2,
        ),
        "transform_max_bbox_error_mm": round(max(transform_errors), 6) if transform_errors else None,
        "model_projection_summaries": model_summaries,
    }


def density_summary_from_export(export_summary: dict[str, Any], grid_mm: float) -> dict[str, Any]:
    build_results: list[dict[str, Any]] = []
    for result in export_summary.get("results", []):
        if not isinstance(result, dict):
            continue
        scene = result.get("scene")
        if not isinstance(scene, dict):
            continue
        density = _scene_density(scene, grid_mm)
        build_results.append(
            {
                "manifest_index": result.get("manifest_index"),
                "scene_id": result.get("scene_id"),
                "case_ids": result.get("case_ids", []),
                "case_count": len(result.get("case_ids", [])),
                "expected_model_count": result.get("expected_model_count"),
                "saved_form": result.get("saved_form"),
                "saved_screenshot": result.get("saved_screenshot"),
                **density,
            }
        )

    average_density = (
        sum(float(result["mesh_projection_density_pct"]) for result in build_results)
        / len(build_results)
        if build_results
        else 0.0
    )
    average_bbox_density = (
        sum(float(result["summed_bbox_density_pct"]) for result in build_results)
        / len(build_results)
        if build_results
        else 0.0
    )
    return {
        "method": "transformed STL vertex projection with one-cell close/fill/open per model",
        "grid_mm": grid_mm,
        "platform": {
            "printer": "Form 4BL",
            "x_mm": FORM4BL_PLATFORM_X_MM,
            "y_mm": FORM4BL_PLATFORM_Y_MM,
            "area_mm2": FORM4BL_PLATFORM_AREA_MM2,
        },
        "build_count": len(build_results),
        "average_mesh_projection_density_pct": round(average_density, 2),
        "average_summed_bbox_density_pct": round(average_bbox_density, 2),
        "results": build_results,
    }


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
    parser.add_argument("--export-folder", type=Path)
    parser.add_argument("--density-output-json", type=Path)
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
    if args.export_folder is not None:
        export_summary = export_form4bl_builds(
            rows,
            args.preform_url.rstrip("/"),
            args.export_folder,
        )
        print(json.dumps({k: v for k, v in export_summary.items() if k != "results"}, indent=2))
        if args.density_output_json is not None:
            density_summary = density_summary_from_export(
                export_summary,
                MESH_RASTER_GRID_MM,
            )
            args.density_output_json.parent.mkdir(parents=True, exist_ok=True)
            args.density_output_json.write_text(
                json.dumps(density_summary, indent=2),
                encoding="utf-8",
            )
            print(json.dumps({k: v for k, v in density_summary.items() if k != "results"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
