from __future__ import annotations

import hashlib
import html
from pathlib import Path
import json
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple
import logging

import numpy as np

# Add repo root to path for core module imports
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.andent_classification import (
    ARTIFACT_ANTAGONIST,
    ARTIFACT_MODEL,
    ARTIFACT_MODEL_BASE,
    ARTIFACT_MODEL_DIE,
    ARTIFACT_SPLINT,
    ARTIFACT_TOOTH,
    STRUCTURE_HOLLOW,
    STRUCTURE_REVIEW,
    STRUCTURE_SOLID,
    WORKFLOW_ORTHO_IMPLANT,
    WORKFLOW_SPLINT,
    classify_artifact,
    extract_case_id,
    measure_mesh_thickness_stats,
    resolve_ortho_structure,
)
from core.batch_optimizer import get_stl_dimensions, get_stl_volume_ml
from stl import mesh as stl_mesh_module
from core.stl_validator import validate_stl_file

from ..schemas import ClassificationRow, DimensionSummary
from .preset_catalog import get_preset_profile


PHASE0_MODEL_TYPES = (
    "Ortho - Solid",
    "Ortho - Hollow",
    "Die",
    "Tooth",
    "Splint",
    "Antagonist",
)

THUMBNAIL_SVG_VERSION = "thumb-v3"


def sanitize_filename(filename: str | None) -> str:
    candidate = Path(filename or "upload.stl").name.strip()
    return candidate or "upload.stl"


def dedupe_filename(filename: str, seen_names: dict[str, int]) -> str:
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    count = seen_names.get(filename.lower(), 0)
    seen_names[filename.lower()] = count + 1
    if count == 0:
        return filename
    return f"{stem}_{count + 1}{suffix}"


def file_content_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def infer_phase0_model_type(file_name: str, artifact, structure=None) -> str | None:
    if artifact.workflow == WORKFLOW_SPLINT or artifact.artifact_type == ARTIFACT_SPLINT:
        return "Splint"
    if artifact.artifact_type == ARTIFACT_MODEL_DIE:
        return "Die"
    if artifact.artifact_type == ARTIFACT_TOOTH:
        return "Tooth"
    if artifact.artifact_type == ARTIFACT_ANTAGONIST:
        return "Antagonist"
    if structure and structure.structure == STRUCTURE_HOLLOW:
        return "Ortho - Hollow"
    if structure and structure.structure == STRUCTURE_SOLID:
        return "Ortho - Solid"
    # Fallback for unsectioned models: default to solid (most common)
    if artifact.artifact_type == ARTIFACT_MODEL and "unsectioned" in file_name.lower():
        return "Ortho - Solid"
    if artifact.workflow == WORKFLOW_ORTHO_IMPLANT or artifact.artifact_type in {ARTIFACT_MODEL, ARTIFACT_MODEL_BASE}:
        return None
    return None


def default_preset(model_type: str | None) -> str | None:
    if model_type is None:
        return None
    preset_mappings = {
        "Ortho - Solid": "Ortho Solid - Flat, No Supports",
        "Ortho - Hollow": "Ortho Hollow - Flat, No Supports",
        "Die": "Die - Flat, No Supports",
        "Tooth": "Tooth - With Supports",
        "Splint": "Splint - Flat, No Supports",
        "Antagonist": "Ortho Solid - Flat, No Supports",
        "Antagonist - Solid": "Antagonist Solid - Flat, No Supports",
        "Antagonist - Hollow": "Antagonist Hollow - Flat, No Supports",
    }
    preset = preset_mappings.get(model_type)
    if preset is None:
        return None
    profile = get_preset_profile(preset)
    if profile is None:
        return None
    return profile.preset_name


def derive_confidence(
    model_type: str | None,
    classifier_confidence: str,
    case_id: str | None,
    *,
    upstream_review_required: bool = False,
) -> str:
    if upstream_review_required:
        return "low"
    if model_type is None:
        return "low"
    if classifier_confidence == "high" and case_id:
        return "high"
    return "medium"


def derive_status(
    confidence: str,
    model_type: str | None,
    preset: str | None,
    *,
    forced_duplicate: bool = False,
    forced_submitted: bool = False,
    manual_override: bool = False,
) -> str:
    if forced_submitted:
        return "Submitted"
    if forced_duplicate:
        return "Duplicate"
    if manual_override and model_type and preset:
        return "Ready"
    if confidence == "high":
        return "Ready"
    if confidence == "medium":
        return "Check"
    return "Needs Review"


def _dimensions_to_summary(dimensions) -> DimensionSummary | None:
    if not dimensions:
        return None

    return DimensionSummary(
        x_mm=round(dimensions.x_mm, 2),
        y_mm=round(dimensions.y_mm, 2),
        z_mm=round(dimensions.z_mm, 2),
    )


def classify_saved_upload(stored_path: Path, original_filename: str) -> ClassificationRow:
    validation = validate_stl_file(str(stored_path))
    if not validation.is_valid:
        raise ValueError(validation.message)

    dimensions = get_stl_dimensions(str(stored_path))
    artifact = classify_artifact(original_filename, dims=dimensions)
    structure = None
    needs_structure_sampling = (
        artifact.artifact_type in {ARTIFACT_MODEL, ARTIFACT_MODEL_BASE}
        and "unsectionedmodel" not in original_filename.lower()
    )
    volume_ml = get_stl_volume_ml(str(stored_path)) if needs_structure_sampling else None
    if needs_structure_sampling:
        thickness_stats = measure_mesh_thickness_stats(str(stored_path))
        structure = resolve_ortho_structure(
            artifact,
            dims=dimensions,
            volume_ml=volume_ml,
            thickness_stats=thickness_stats,
        )
    model_type = infer_phase0_model_type(original_filename, artifact, structure)
    preset = default_preset(model_type)
    review_required = bool(artifact.review_required or artifact.review_reason or model_type is None)
    confidence = derive_confidence(
        model_type,
        artifact.confidence,
        artifact.case_id,
        upstream_review_required=review_required,
    )

    review_reason = artifact.review_reason
    if structure and not review_reason and structure.structure == STRUCTURE_REVIEW:
        review_reason = structure.reason
    elif not review_reason and model_type is None:
        review_reason = "Unable to map artifact into the approved Phase 0 model types."
    elif not review_reason and confidence == "medium":
        review_reason = "Model type inferred from weaker signals and should be checked."
    elif not review_reason and confidence == "low":
        review_reason = "Unable to classify artifact confidently from filename or geometry."
    review_required = review_required or confidence != "high" or model_type is None

    case_id = artifact.case_id
    if not case_id:
        if not review_reason:
            review_reason = "Case ID could not be detected from filename."
        else:
            review_reason = review_reason + "; Case ID missing"

    return ClassificationRow(
        file_name=original_filename,
        case_id=artifact.case_id,
        model_type=model_type,
        preset=preset,
        confidence=confidence,
        status=derive_status(confidence, model_type, preset),
        dimensions=_dimensions_to_summary(dimensions),
        volume_ml=volume_ml,
        structure=structure.structure if structure else None,
        structure_confidence=structure.confidence if structure else None,
        structure_reason=structure.reason if structure else None,
        structure_metrics=structure.metrics if structure else None,
        structure_locked=structure.locked if structure else False,
        review_required=review_required,
        review_reason=review_reason,
    )


def serialize_row_for_storage(row: ClassificationRow, stored_path: Path, content_hash: str) -> dict:
    return {
        "file_name": row.file_name,
        "stored_path": str(stored_path),
        "content_hash": content_hash,
        "thumbnail_svg": None,
        "case_id": row.case_id,
        "model_type": row.model_type,
        "preset": row.preset,
        "confidence": row.confidence,
        "status": row.status,
        "dimension_x_mm": row.dimensions.x_mm if row.dimensions else None,
        "dimension_y_mm": row.dimensions.y_mm if row.dimensions else None,
        "dimension_z_mm": row.dimensions.z_mm if row.dimensions else None,
        "volume_ml": row.volume_ml,
        "structure": row.structure,
        "structure_confidence": row.structure_confidence,
        "structure_reason": row.structure_reason,
        "structure_metrics_json": json.dumps(row.structure_metrics) if row.structure_metrics is not None else None,
        "structure_locked": row.structure_locked,
        "review_required": row.review_required,
        "review_reason": row.review_reason,
    }


def _box_filter(values: np.ndarray) -> np.ndarray:
    padded = np.pad(values, 1, mode="constant")
    return (
        padded[:-2, :-2]
        + padded[:-2, 1:-1]
        + padded[:-2, 2:]
        + padded[1:-1, :-2]
        + padded[1:-1, 1:-1]
        + padded[1:-1, 2:]
        + padded[2:, :-2]
        + padded[2:, 1:-1]
        + padded[2:, 2:]
    ) / 9.0


def _dilate_mask(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask, 1, mode="constant")
    return (
        padded[:-2, :-2]
        | padded[:-2, 1:-1]
        | padded[:-2, 2:]
        | padded[1:-1, :-2]
        | padded[1:-1, 1:-1]
        | padded[1:-1, 2:]
        | padded[2:, :-2]
        | padded[2:, 1:-1]
        | padded[2:, 2:]
    )


def _connected_component_score(mask: np.ndarray) -> float:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    largest = 0
    components = 0
    for start_y, start_x in np.argwhere(mask):
        if visited[start_y, start_x]:
            continue
        components += 1
        stack = [(int(start_y), int(start_x))]
        visited[start_y, start_x] = True
        size = 0
        while stack:
            y, x = stack.pop()
            size += 1
            for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= next_y < height and 0 <= next_x < width and mask[next_y, next_x] and not visited[next_y, next_x]:
                    visited[next_y, next_x] = True
                    stack.append((next_y, next_x))
        largest = max(largest, size)
    filled = int(mask.sum())
    if filled == 0:
        return float("-inf")
    coverage = filled / float(height * width)
    bbox_points = np.argwhere(mask)
    bbox_height = bbox_points[:, 0].max() - bbox_points[:, 0].min() + 1
    bbox_width = bbox_points[:, 1].max() - bbox_points[:, 1].min() + 1
    bbox_area = max(int(bbox_height * bbox_width), 1)
    solidity = filled / float(bbox_area)
    return (
        largest * 1.1
        + filled * 0.24
        + solidity * 140.0
        - components * 28.0
        - abs(coverage - 0.2) * 420.0
    )


def is_current_thumbnail_svg(svg: str | None) -> bool:
    return bool(svg and THUMBNAIL_SVG_VERSION in svg)


def _raster_to_svg(mask: np.ndarray, shade_map: np.ndarray, *, output_size: int, viewbox_size: int, background: str) -> str:
    rows: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" data-thumbnail-version="{THUMBNAIL_SVG_VERSION}" '
        f'width="{output_size}" height="{output_size}" viewBox="0 0 {viewbox_size} {viewbox_size}">',
        f'<rect width="{viewbox_size}" height="{viewbox_size}" rx="18" fill="{background}" />',
    ]
    for y in range(viewbox_size):
        x = 0
        while x < viewbox_size:
            if not mask[y, x]:
                x += 1
                continue
            shade = int(shade_map[y, x])
            start_x = x
            x += 1
            while x < viewbox_size and mask[y, x] and int(shade_map[y, x]) == shade:
                x += 1
            rows.append(
                f'<rect x="{start_x}" y="{y}" width="{x - start_x}" height="1" '
                f'fill="rgb({shade}, {max(shade - 24, 48)}, {max(shade - 46, 32)})" />'
            )
    rows.append("</svg>")
    return "".join(rows)


def _rotation_matrix(x_angle: float, y_angle: float, z_angle: float = 0.0) -> np.ndarray:
    cx, sx = np.cos(x_angle), np.sin(x_angle)
    cy, sy = np.cos(y_angle), np.sin(y_angle)
    cz, sz = np.cos(z_angle), np.sin(z_angle)
    rotate_x = np.array(((1.0, 0.0, 0.0), (0.0, cx, -sx), (0.0, sx, cx)))
    rotate_y = np.array(((cy, 0.0, sy), (0.0, 1.0, 0.0), (-sy, 0.0, cy)))
    rotate_z = np.array(((cz, -sz, 0.0), (sz, cz, 0.0), (0.0, 0.0, 1.0)))
    return rotate_z @ rotate_y @ rotate_x


def _align_triangles_to_principal_axes(triangles: np.ndarray) -> np.ndarray:
    points = triangles.reshape(-1, 3)
    covariance = np.cov(points.T)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(eigenvalues)[::-1]
    basis = eigenvectors[:, order]
    if np.linalg.det(basis) < 0:
        basis[:, 2] *= -1.0
    return triangles @ basis


def _render_thumbnail_view(
    triangles: np.ndarray,
    *,
    rotation: tuple[float, float, float],
    render_size: int,
) -> tuple[np.ndarray, np.ndarray, float]:
    rotated = triangles @ _rotation_matrix(*rotation).T
    points = rotated.reshape(-1, 3)
    min_bounds = points.min(axis=0)
    max_bounds = points.max(axis=0)
    max_span = max(float((max_bounds - min_bounds).max()), 1.0)

    camera_distance = max_span * 3.6
    perspective = camera_distance / np.maximum(camera_distance - rotated[:, :, 2], max_span * 0.25)
    px = rotated[:, :, 0] * perspective
    py = rotated[:, :, 1] * perspective

    min_x = float(px.min())
    max_x = float(px.max())
    min_y = float(py.min())
    max_y = float(py.max())
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    padding = render_size * 0.12
    scale = min((render_size - padding * 2) / width, (render_size - padding * 2) / height)
    offset_x = (render_size - width * scale) * 0.5
    offset_y = (render_size - height * scale) * 0.5
    screen_x = (px - min_x) * scale + offset_x
    screen_y = (py - min_y) * scale + offset_y

    normals = np.cross(rotated[:, 1] - rotated[:, 0], rotated[:, 2] - rotated[:, 0])
    normal_lengths = np.linalg.norm(normals, axis=1)
    valid_normals = normal_lengths > 1e-9
    normal_lengths[~valid_normals] = 1.0
    light_direction = np.array([0.28, 0.35, 0.9], dtype=float)
    light_direction /= np.linalg.norm(light_direction)
    light_strength = np.clip((normals / normal_lengths[:, None]) @ light_direction, 0.0, 1.0)
    light_strength = np.where(valid_normals, light_strength, 0.35)
    depth = rotated[:, :, 2].mean(axis=1)
    depth_min = float(depth.min())
    depth_span = max(float(depth.max()) - depth_min, 1e-6)
    depth_norm = (depth - depth_min) / depth_span
    triangle_shades = np.clip(92 + light_strength * 78 + depth_norm * 20, 86, 188)

    density = np.zeros((render_size, render_size), dtype=float)
    shade_sum = np.zeros((render_size, render_size), dtype=float)
    shade_weight = np.zeros((render_size, render_size), dtype=float)

    edge01 = np.sqrt((screen_x[:, 0] - screen_x[:, 1]) ** 2 + (screen_y[:, 0] - screen_y[:, 1]) ** 2)
    edge12 = np.sqrt((screen_x[:, 1] - screen_x[:, 2]) ** 2 + (screen_y[:, 1] - screen_y[:, 2]) ** 2)
    edge20 = np.sqrt((screen_x[:, 2] - screen_x[:, 0]) ** 2 + (screen_y[:, 2] - screen_y[:, 0]) ** 2)
    max_edge = np.maximum(np.maximum(edge01, edge12), edge20)
    bbox_area = (screen_x.max(axis=1) - screen_x.min(axis=1)) * (screen_y.max(axis=1) - screen_y.min(axis=1))
    small_mask = (max_edge <= 1.35) | (bbox_area <= 2.0)

    if np.any(small_mask):
        centroid_x = np.clip(np.rint(screen_x[small_mask].mean(axis=1)).astype(int), 1, render_size - 2)
        centroid_y = np.clip(np.rint(screen_y[small_mask].mean(axis=1)).astype(int), 1, render_size - 2)
        np.add.at(density, (centroid_y, centroid_x), 1.0)
        np.add.at(shade_sum, (centroid_y, centroid_x), triangle_shades[small_mask])
        np.add.at(shade_weight, (centroid_y, centroid_x), 1.0)

    large_indices = np.nonzero(~small_mask)[0]
    for index in large_indices:
        x0, x1, x2 = screen_x[index]
        y0, y1, y2 = screen_y[index]
        min_px = max(0, int(np.floor(min(x0, x1, x2))))
        max_px = min(render_size - 1, int(np.ceil(max(x0, x1, x2))))
        min_py = max(0, int(np.floor(min(y0, y1, y2))))
        max_py = min(render_size - 1, int(np.ceil(max(y0, y1, y2))))
        if min_px > max_px or min_py > max_py:
            continue
        denominator = ((y1 - y2) * (x0 - x2)) + ((x2 - x1) * (y0 - y2))
        if abs(denominator) < 1e-9:
            continue

        grid_x, grid_y = np.meshgrid(
            np.arange(min_px, max_px + 1, dtype=float) + 0.5,
            np.arange(min_py, max_py + 1, dtype=float) + 0.5,
        )
        bary_a = (((y1 - y2) * (grid_x - x2)) + ((x2 - x1) * (grid_y - y2))) / denominator
        bary_b = (((y2 - y0) * (grid_x - x2)) + ((x0 - x2) * (grid_y - y2))) / denominator
        bary_c = 1.0 - bary_a - bary_b
        inside = (bary_a >= -1e-6) & (bary_b >= -1e-6) & (bary_c >= -1e-6)
        if not inside.any():
            continue

        density_slice = density[min_py : max_py + 1, min_px : max_px + 1]
        shade_sum_slice = shade_sum[min_py : max_py + 1, min_px : max_px + 1]
        shade_weight_slice = shade_weight[min_py : max_py + 1, min_px : max_px + 1]
        density_slice[inside] += 3.4
        shade_sum_slice[inside] += float(triangle_shades[index]) * 3.4
        shade_weight_slice[inside] += 3.4

    density = _box_filter(_box_filter(density))
    shade_sum = _box_filter(_box_filter(shade_sum))
    shade_weight = _box_filter(_box_filter(shade_weight))
    if float(density.max()) <= 0.0:
        empty = np.zeros((render_size, render_size), dtype=bool)
        return empty, np.zeros((render_size, render_size), dtype=int), float("-inf")

    density_norm = density / float(density.max())
    mask = density_norm > 0.14
    if not mask.any():
        mask = density_norm > 0.05
    mask = _dilate_mask(mask)

    average_shade = np.divide(shade_sum, np.maximum(shade_weight, 1e-6))
    shade_map = np.clip(average_shade * (0.78 + density_norm * 0.34), 88, 190).astype(int)
    return mask, shade_map, _connected_component_score(mask)


def generate_thumbnail_svg(stored_path: Path, size: int = 84) -> str:
    background = "#F3E7D9"
    try:
        stl_mesh = stl_mesh_module.Mesh.from_file(str(stored_path))
        triangles = np.asarray(stl_mesh.vectors, dtype=float)
    except Exception:
        label = html.escape(stored_path.suffix.upper().lstrip(".") or "STL")
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" data-thumbnail-version="{THUMBNAIL_SVG_VERSION}" '
            f'width="{size}" height="{size}" '
            f'viewBox="0 0 {size} {size}">'
            f'<rect width="{size}" height="{size}" rx="12" fill="{background}" />'
            f'<text x="50%" y="54%" text-anchor="middle" font-size="16" '
            f'font-family="Inter, sans-serif" fill="#6B563D">{label}</text>'
            f"</svg>"
        )

    if triangles.size == 0:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" data-thumbnail-version="{THUMBNAIL_SVG_VERSION}" width="{size}" height="{size}" '
            f'viewBox="0 0 {size} {size}"><rect width="{size}" height="{size}" rx="12" fill="{background}" /></svg>'
        )

    centered = triangles - triangles.reshape(-1, 3).mean(axis=0)
    aligned = _align_triangles_to_principal_axes(centered)
    render_size = 128
    candidate_rotations = (
        (-0.62, -0.55, 0.0),
        (-0.48, 0.0, 0.0),
        (-0.34, 0.0, 0.0),
        (-0.22, 0.38, 0.0),
        (-0.62, 3.14159 - 0.55, 0.0),
        (-0.48, 3.14159, 0.0),
        (-0.34, 3.14159, 0.0),
        (-0.22, 3.14159 + 0.38, 0.0),
    )

    best_mask = np.zeros((render_size, render_size), dtype=bool)
    best_shade_map = np.zeros((render_size, render_size), dtype=int)
    best_score = float("-inf")
    for rotation in candidate_rotations:
        mask, shade_map, score = _render_thumbnail_view(aligned, rotation=rotation, render_size=render_size)
        if score > best_score:
            best_mask = mask
            best_shade_map = shade_map
            best_score = score

    if best_score == float("-inf") or not best_mask.any():
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" data-thumbnail-version="{THUMBNAIL_SVG_VERSION}" width="{size}" height="{size}" '
            f'viewBox="0 0 {size} {size}"><rect width="{size}" height="{size}" rx="12" fill="{background}" /></svg>'
        )

    return _raster_to_svg(best_mask, best_shade_map, output_size=size, viewbox_size=render_size, background=background)


def classify_uploaded_files_parallel(
    files: List[Tuple[Path, str]],
    max_workers: int = 4,
) -> List[ClassificationRow]:
    """
    Classify multiple STL files in parallel.
    
    Args:
        files: List of (stored_path, original_filename) tuples
        max_workers: Maximum number of parallel workers
    
    Returns:
        List of ClassificationRow results
    """
    results: List[ClassificationRow | None] = [None] * len(files)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all classification tasks
        future_to_file = {
            executor.submit(classify_saved_upload, stored_path, filename): (index, stored_path, filename)
            for index, (stored_path, filename) in enumerate(files)
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_file):
            index, stored_path, filename = future_to_file[future]
            try:
                result = future.result()
                results[index] = result
                logging.debug(f"Classified {filename} successfully")
            except Exception as exc:
                logging.error(f"Failed to classify {filename}: {exc}")
                # Add error row instead of failing entire batch
                results[index] = ClassificationRow(
                    file_name=filename,
                    case_id=extract_case_id(filename),
                    model_type=None,
                    preset=None,
                    confidence="low",
                    status="Needs Review",
                    review_required=True,
                    review_reason=f"Classification failed: {exc}",
                )
    
    return [result for result in results if result is not None]
