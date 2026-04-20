import logging
import os
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, List, Optional

import numpy as np

from .batch_optimizer import STLDimensions, get_stl_dimensions, get_stl_volume_ml
from .cache import get_cache
from stl import mesh as stl_mesh_module

WORKFLOW_STANDARD = "standard"
WORKFLOW_ORTHO_IMPLANT = "ortho_implant"
WORKFLOW_TOOTH_MODEL = "tooth_model"
WORKFLOW_ORTHO_TOOTH = "ortho_tooth"
WORKFLOW_SPLINT = "splint"
WORKFLOW_MANUAL_REVIEW = "manual_review"

ARTIFACT_MODEL = "model"
ARTIFACT_TOOTH = "tooth"
ARTIFACT_SPLINT = "splint"
ARTIFACT_ANTAGONIST = "antagonist"
ARTIFACT_MODEL_BASE = "model_base"
ARTIFACT_MODEL_DIE = "model_die"
ARTIFACT_UNKNOWN = "unknown"

STRUCTURE_SOLID = "solid"
STRUCTURE_HOLLOW = "hollow"
STRUCTURE_REVIEW = "review"

THICKNESS_SAMPLE_BUDGET = None
THICKNESS_SAMPLE_BUDGET_MIN = 24
THICKNESS_SAMPLE_BUDGET_MAX = 64
THICKNESS_MIN_SAMPLE_COUNT = 16
THICKNESS_MIN_VALID_SAMPLE_FRACTION = 0.25
THICKNESS_MIN_HIT_DISTANCE_MM = 0.2
HOLLOW_MAX_FILL_RATIO = 0.32
SOLID_MIN_FILL_RATIO = 0.28
HOLLOW_MAX_P10_MM = 3.5
HOLLOW_MAX_P50_MM = 5.0
HOLLOW_MIN_THIN_FRACTION_UNDER_5MM = 0.65
SOLID_MIN_P10_MM = 3.0
SOLID_MIN_P50_MM = 5.0
SOLID_MAX_THIN_FRACTION_UNDER_5MM = 0.60

_DATE_TOKEN_RE = re.compile(r"^\d{8}$|^\d{4}-\d{2}-\d{2}$")
_RESERVED_CASE_TOKENS = {
    "antag",
    "antagonist",
    "biteguard",
    "bitesplint",
    "guard",
    "lowerjaw",
    "model",
    "modelbase",
    "modeldie",
    "splint",
    "tooth",
    "upperjaw",
    "unsectionedmodel",
}


@dataclass
class ArtifactClassification:
    file_path: str
    case_id: Optional[str]
    artifact_type: str
    workflow: str
    confidence: str
    reasons: List[str] = field(default_factory=list)
    review_required: bool = False
    review_reason: Optional[str] = None
    dimensions: Optional[STLDimensions] = None


@dataclass
class StructureResolution:
    structure: str
    confidence: str
    reason: str
    fill_ratio: Optional[float] = None
    geometry_derived: bool = False
    locked: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThicknessStats:
    sample_count: int
    valid_sample_count: int
    valid_sample_fraction: float
    thickness_p10: Optional[float] = None
    thickness_p50: Optional[float] = None
    thin_fraction_under_5mm: Optional[float] = None
    thin_fraction_under_3mm: Optional[float] = None
    manifold_edge_fraction: Optional[float] = None
    boundary_edge_count: int = 0
    non_manifold_edge_count: int = 0
    reason: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "valid_sample_count": self.valid_sample_count,
            "valid_sample_fraction": round(self.valid_sample_fraction, 4),
            "thickness_p10": self.thickness_p10,
            "thickness_p50": self.thickness_p50,
            "thin_fraction_under_5mm": self.thin_fraction_under_5mm,
            "thin_fraction_under_3mm": self.thin_fraction_under_3mm,
            "manifold_edge_fraction": self.manifold_edge_fraction,
            "boundary_edge_count": self.boundary_edge_count,
            "non_manifold_edge_count": self.non_manifold_edge_count,
            "reason": self.reason,
        }


def _normalize_case_token(token: str) -> Optional[str]:
    normalized = re.sub(r"[^A-Za-z0-9-]+", "", token).strip("-_").upper()
    if len(normalized) < 3 or normalized.lower() in _RESERVED_CASE_TOKENS:
        return None
    if not any(char.isdigit() for char in normalized):
        return None
    return normalized


def _is_valid_compact_date(token: str) -> bool:
    if len(token) != 8 or not token.isdigit():
        return False
    try:
        datetime.strptime(token, "%Y%m%d")
    except ValueError:
        return False
    return True


def _has_legacy_arch_suffix(name: str) -> bool:
    return re.search(r"(?:^|[_\-\s])(upper|lower|u|l)$", name) is not None


def extract_case_id(file_path: str) -> Optional[str]:
    stem = os.path.splitext(os.path.basename(file_path))[0]
    embedded_numeric_ids = [
        match.group(1)
        for match in re.finditer(r"(?<!\d)(\d{7,8})(?!\d)", stem)
        if not _is_valid_compact_date(match.group(1))
    ]
    if embedded_numeric_ids:
        return embedded_numeric_ids[0]

    parts = [part for part in stem.split("_") if part]
    if not parts:
        return None

    if _DATE_TOKEN_RE.match(parts[0]):
        if len(parts) < 2:
            return None
        dated_token = parts[1]
        if "-" in dated_token:
            dated_parts = [part for part in dated_token.split("-") if part]
            if len(dated_parts) >= 3:
                token = _normalize_case_token(dated_parts[-1])
                if token:
                    return token
        return _normalize_case_token(dated_token)

    if len(parts) >= 2 and _DATE_TOKEN_RE.match(parts[1]):
        return _normalize_case_token(parts[0])

    return _normalize_case_token(parts[0])


def classify_artifact(file_path: str, dims: Optional[STLDimensions] = None) -> ArtifactClassification:
    case_id = extract_case_id(file_path)
    name = os.path.splitext(os.path.basename(file_path))[0].lower()
    reasons: List[str] = []
    artifact_type = ARTIFACT_UNKNOWN
    workflow = WORKFLOW_MANUAL_REVIEW
    confidence = "high"
    review_reason = None

    if any(keyword in name for keyword in ("bitesplint", "biteguard", "bite_guard", "nightguard", "splint")):
        artifact_type = ARTIFACT_SPLINT
        workflow = WORKFLOW_SPLINT
        reasons.append("filename matched splint/bite-guard keywords")
    elif "modeldie" in name or re.search(r"(^|[_-])die([_-]|$)", name):
        artifact_type = ARTIFACT_MODEL_DIE
        workflow = WORKFLOW_ORTHO_IMPLANT
        reasons.append("filename matched die/model-die keyword")
    elif re.search(r"(^|[_-])tooth([_-]|$)", name):
        artifact_type = ARTIFACT_TOOTH
        workflow = WORKFLOW_TOOTH_MODEL
        reasons.append("filename matched tooth keyword")
    elif "modelbase" in name:
        artifact_type = ARTIFACT_MODEL_BASE
        workflow = WORKFLOW_ORTHO_IMPLANT
        reasons.append("filename matched model base keyword")
    elif any(keyword in name for keyword in ("antag", "antagonist")):
        artifact_type = ARTIFACT_ANTAGONIST
        workflow = WORKFLOW_ORTHO_IMPLANT
        reasons.append("filename matched antagonist keyword")
    elif _has_legacy_arch_suffix(name):
        artifact_type = ARTIFACT_MODEL
        workflow = WORKFLOW_ORTHO_IMPLANT
        reasons.append("filename matched legacy upper/lower arch suffix")
    elif any(keyword in name for keyword in ("unsectionedmodel", "upperjaw", "lowerjaw", "implant", "model")):
        artifact_type = ARTIFACT_MODEL
        workflow = WORKFLOW_ORTHO_IMPLANT
        reasons.append("filename matched model/arch keywords")
    else:
        dims = dims or get_stl_dimensions(file_path)
        if dims and max(dims.x_mm, dims.y_mm) <= 35.0 and dims.z_mm <= 35.0:
            artifact_type = ARTIFACT_TOOTH
            workflow = WORKFLOW_TOOTH_MODEL
            confidence = "low"
            reasons.append("small geometry fallback matched likely tooth artifact")
        elif dims and dims.z_mm <= 8.0 and max(dims.x_mm, dims.y_mm) >= 40.0:
            artifact_type = ARTIFACT_SPLINT
            workflow = WORKFLOW_SPLINT
            confidence = "low"
            reasons.append("thin geometry fallback matched likely splint artifact")
        elif dims and max(dims.x_mm, dims.y_mm) >= 45.0:
            artifact_type = ARTIFACT_MODEL
            workflow = WORKFLOW_ORTHO_IMPLANT
            confidence = "low"
            reasons.append("large geometry fallback matched likely model artifact")
        else:
            review_reason = "Unable to classify artifact confidently from filename or geometry."

    review_required = review_reason is not None
    if not case_id and not review_required:
        review_required = True
        review_reason = "Could not derive a stable case identifier from the filename."

    return ArtifactClassification(
        file_path=file_path,
        case_id=case_id,
        artifact_type=artifact_type,
        workflow=workflow,
        confidence=confidence,
        reasons=reasons,
        review_required=review_required,
        review_reason=review_reason,
        dimensions=dims,
    )


def _bbox_volume_ml(dims: Optional[STLDimensions]) -> Optional[float]:
    if dims is None:
        return None
    volume_ml = (dims.x_mm * dims.y_mm * dims.z_mm) / 1000.0
    if volume_ml <= 0:
        return None
    return float(volume_ml)


def _round_metric(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 4)


def _weighted_sample_indices(weights: np.ndarray, sample_budget: int) -> np.ndarray:
    if weights.size == 0:
        return np.array([], dtype=int)
    count = min(sample_budget, weights.size)
    cumulative = np.cumsum(weights)
    if cumulative[-1] <= 0:
        return np.array([], dtype=int)
    targets = ((np.arange(count) + 0.5) / count) * cumulative[-1]
    return np.searchsorted(cumulative, targets, side="left")


def _edge_topology_stats(triangles: np.ndarray) -> tuple[Optional[float], int, int]:
    if triangles.size == 0:
        return None, 0, 0

    edge_counts: dict[tuple[tuple[float, float, float], tuple[float, float, float]], int] = {}
    rounded = np.round(triangles, 5)
    for triangle in rounded:
        vertices = [tuple(float(component) for component in vertex) for vertex in triangle]
        for start, end in ((0, 1), (1, 2), (2, 0)):
            edge = tuple(sorted((vertices[start], vertices[end])))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1

    if not edge_counts:
        return None, 0, 0

    boundary_edge_count = sum(1 for count in edge_counts.values() if count == 1)
    non_manifold_edge_count = sum(1 for count in edge_counts.values() if count > 2)
    manifold_edge_fraction = _round_metric(sum(1 for count in edge_counts.values() if count == 2) / len(edge_counts))
    return manifold_edge_fraction, boundary_edge_count, non_manifold_edge_count


def _first_ray_hit_distance(
    origin: np.ndarray,
    direction: np.ndarray,
    triangles: np.ndarray,
    *,
    exclude_index: int,
    min_distance_mm: float,
) -> Optional[float]:
    if triangles.size == 0:
        return None

    v0 = triangles[:, 0]
    edge1 = triangles[:, 1] - v0
    edge2 = triangles[:, 2] - v0
    direction_stack = np.broadcast_to(direction, edge2.shape)
    pvec = np.cross(direction_stack, edge2)
    det = np.einsum("ij,ij->i", edge1, pvec)
    valid = np.abs(det) > 1e-9
    if 0 <= exclude_index < valid.size:
        valid[exclude_index] = False
    if not np.any(valid):
        return None

    inv_det = np.zeros_like(det)
    inv_det[valid] = 1.0 / det[valid]
    tvec = origin - v0
    u = inv_det * np.einsum("ij,ij->i", tvec, pvec)
    valid &= (u >= -1e-8) & (u <= 1.0 + 1e-8)
    if not np.any(valid):
        return None

    qvec = np.cross(tvec, edge1)
    v = inv_det * np.einsum("ij,ij->i", direction_stack, qvec)
    valid &= (v >= -1e-8) & ((u + v) <= 1.0 + 1e-8)
    if not np.any(valid):
        return None

    t = inv_det * np.einsum("ij,ij->i", edge2, qvec)
    valid &= t > min_distance_mm
    if not np.any(valid):
        return None

    return float(np.min(t[valid]))


def measure_mesh_thickness_stats(
    file_path: str,
    *,
    sample_budget: int = THICKNESS_SAMPLE_BUDGET,
    min_hit_distance_mm: float = THICKNESS_MIN_HIT_DISTANCE_MM,
) -> ThicknessStats:
    use_cache = sample_budget is None
    cache = get_cache()
    if use_cache:
        cached = cache.get_thickness(file_path)
        if cached:
            logging.debug(f"Cache hit for thickness: {os.path.basename(file_path)}")
            return ThicknessStats(**cached)

    def _finalize(result: ThicknessStats) -> ThicknessStats:
        if use_cache:
            cache.set_thickness(file_path, result.as_dict())
        return result

    try:
        stl_mesh = stl_mesh_module.Mesh.from_file(file_path)
        triangles = np.asarray(stl_mesh.vectors, dtype=float)
    except Exception as exc:
        return _finalize(ThicknessStats(
            sample_count=0,
            valid_sample_count=0,
            valid_sample_fraction=0.0,
            reason=f"Mesh loading failed: {exc}",
        ))

    if triangles.size == 0:
        return _finalize(ThicknessStats(
            sample_count=0,
            valid_sample_count=0,
            valid_sample_fraction=0.0,
            reason="Mesh has no triangles.",
        ))

    triangle_count = len(triangles)
    if sample_budget is None:
        if triangle_count < 500:
            sample_budget = THICKNESS_SAMPLE_BUDGET_MIN
        elif triangle_count < 2000:
            sample_budget = 40
        else:
            sample_budget = THICKNESS_SAMPLE_BUDGET_MAX

    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    doubled_areas = np.linalg.norm(normals, axis=1)
    valid_triangles = doubled_areas > 1e-8
    manifold_edge_fraction, boundary_edge_count, non_manifold_edge_count = _edge_topology_stats(triangles)
    if not np.any(valid_triangles):
        return _finalize(ThicknessStats(
            sample_count=0,
            valid_sample_count=0,
            valid_sample_fraction=0.0,
            manifold_edge_fraction=manifold_edge_fraction,
            boundary_edge_count=boundary_edge_count,
            non_manifold_edge_count=non_manifold_edge_count,
            reason="Mesh has no valid triangle areas for thickness sampling.",
        ))

    valid_indices = np.flatnonzero(valid_triangles)
    sample_pick = _weighted_sample_indices(doubled_areas[valid_triangles], sample_budget)
    if sample_pick.size == 0:
        return _finalize(ThicknessStats(
            sample_count=0,
            valid_sample_count=0,
            valid_sample_fraction=0.0,
            manifold_edge_fraction=manifold_edge_fraction,
            boundary_edge_count=boundary_edge_count,
            non_manifold_edge_count=non_manifold_edge_count,
            reason="Mesh sampling could not select any triangles.",
        ))

    sampled_indices = valid_indices[sample_pick]
    sample_count = int(sampled_indices.size)
    thicknesses: list[float] = []
    unit_normals = normals[valid_triangles] / doubled_areas[valid_triangles][:, None]
    normal_lookup = {triangle_index: unit_normals[pos] for pos, triangle_index in enumerate(valid_indices)}

    for triangle_index in sampled_indices:
        base_normal = normal_lookup[triangle_index]
        if np.linalg.norm(base_normal) <= 1e-9:
            continue
        centroid = triangles[triangle_index].mean(axis=0)
        probe_distances = []
        for direction in (base_normal, -base_normal):
            origin = centroid + direction * 1e-4
            hit_distance = _first_ray_hit_distance(
                origin,
                direction,
                triangles,
                exclude_index=int(triangle_index),
                min_distance_mm=min_hit_distance_mm,
            )
            if hit_distance is not None:
                probe_distances.append(hit_distance)
        if probe_distances:
            thicknesses.append(min(probe_distances))

    valid_sample_count = len(thicknesses)
    valid_sample_fraction = (valid_sample_count / sample_count) if sample_count else 0.0
    if not thicknesses:
        return _finalize(ThicknessStats(
            sample_count=sample_count,
            valid_sample_count=0,
            valid_sample_fraction=valid_sample_fraction,
            manifold_edge_fraction=manifold_edge_fraction,
            boundary_edge_count=boundary_edge_count,
            non_manifold_edge_count=non_manifold_edge_count,
            reason="No valid inward thickness probes reached an opposite surface.",
        ))

    thickness_array = np.asarray(thicknesses, dtype=float)
    return _finalize(ThicknessStats(
        sample_count=sample_count,
        valid_sample_count=valid_sample_count,
        valid_sample_fraction=valid_sample_fraction,
        thickness_p10=_round_metric(np.percentile(thickness_array, 10)),
        thickness_p50=_round_metric(np.percentile(thickness_array, 50)),
        thin_fraction_under_5mm=_round_metric(np.mean(thickness_array < 5.0)),
        thin_fraction_under_3mm=_round_metric(np.mean(thickness_array < 3.0)),
        manifold_edge_fraction=manifold_edge_fraction,
        boundary_edge_count=boundary_edge_count,
        non_manifold_edge_count=non_manifold_edge_count,
    ))


def _build_structure_metrics(
    *,
    fill_ratio: Optional[float],
    thickness_stats: Optional[ThicknessStats],
) -> dict[str, Any]:
    metrics = {"fill_ratio": _round_metric(fill_ratio)}
    if thickness_stats is not None:
        metrics.update(thickness_stats.as_dict())
    return metrics


def resolve_ortho_structure(
    artifact: ArtifactClassification,
    *,
    dims: Optional[STLDimensions] = None,
    volume_ml: Optional[float] = None,
    thickness_stats: Optional[ThicknessStats] = None,
) -> Optional[StructureResolution]:
    if artifact.artifact_type not in {ARTIFACT_MODEL, ARTIFACT_ANTAGONIST, ARTIFACT_MODEL_BASE}:
        return None

    dims = dims or artifact.dimensions or get_stl_dimensions(artifact.file_path)
    if volume_ml is None:
        volume_ml = get_stl_volume_ml(artifact.file_path)

    bbox_volume_ml = _bbox_volume_ml(dims)
    if bbox_volume_ml is None or volume_ml is None:
        return StructureResolution(
            structure=STRUCTURE_REVIEW,
            confidence="low",
            reason="Missing geometry metrics required for solid/hollow classification.",
            metrics=_build_structure_metrics(fill_ratio=None, thickness_stats=thickness_stats),
        )

    fill_ratio = float(volume_ml) / bbox_volume_ml
    thickness_stats = thickness_stats or measure_mesh_thickness_stats(artifact.file_path)
    metrics = _build_structure_metrics(fill_ratio=fill_ratio, thickness_stats=thickness_stats)

    if (
        thickness_stats.boundary_edge_count > 0
        or thickness_stats.non_manifold_edge_count > 0
        or (
            thickness_stats.manifold_edge_fraction is not None
            and thickness_stats.manifold_edge_fraction < 0.95
        )
    ):
        return StructureResolution(
            structure=STRUCTURE_REVIEW,
            confidence="low",
            reason="Mesh topology is too open or non-manifold for safe wall-thickness classification.",
            fill_ratio=_round_metric(fill_ratio),
            geometry_derived=True,
            metrics=metrics,
        )

    if (
        thickness_stats.sample_count < THICKNESS_MIN_SAMPLE_COUNT
        or thickness_stats.valid_sample_fraction < THICKNESS_MIN_VALID_SAMPLE_FRACTION
        or thickness_stats.thickness_p10 is None
        or thickness_stats.thickness_p50 is None
        or thickness_stats.thin_fraction_under_5mm is None
    ):
        return StructureResolution(
            structure=STRUCTURE_REVIEW,
            confidence="low",
            reason="Thickness sampling quality was too weak for a safe solid/hollow decision.",
            fill_ratio=_round_metric(fill_ratio),
            geometry_derived=True,
            metrics=metrics,
        )

    if (
        fill_ratio <= HOLLOW_MAX_FILL_RATIO
        and thickness_stats.thickness_p10 <= HOLLOW_MAX_P10_MM
        and thickness_stats.thickness_p50 <= HOLLOW_MAX_P50_MM
        and thickness_stats.thin_fraction_under_5mm >= HOLLOW_MIN_THIN_FRACTION_UNDER_5MM
    ):
        return StructureResolution(
            structure=STRUCTURE_HOLLOW,
            confidence="high",
            reason="Fill ratio and wall-thickness evidence both indicate a hollow ortho-style model.",
            fill_ratio=_round_metric(fill_ratio),
            geometry_derived=True,
            metrics=metrics,
        )

    if (
        fill_ratio >= SOLID_MIN_FILL_RATIO
        and thickness_stats.thickness_p10 >= SOLID_MIN_P10_MM
        and thickness_stats.thickness_p50 >= SOLID_MIN_P50_MM
        and thickness_stats.thin_fraction_under_5mm <= SOLID_MAX_THIN_FRACTION_UNDER_5MM
    ):
        return StructureResolution(
            structure=STRUCTURE_SOLID,
            confidence="high",
            reason="Fill ratio and wall-thickness evidence both indicate a solid ortho-style model.",
            fill_ratio=_round_metric(fill_ratio),
            geometry_derived=True,
            metrics=metrics,
        )

    return StructureResolution(
        structure=STRUCTURE_REVIEW,
        confidence="low",
        reason="Fill ratio and wall-thickness evidence did not agree strongly enough for auto-classification.",
        fill_ratio=_round_metric(fill_ratio),
        geometry_derived=True,
        metrics=metrics,
    )


__all__ = [
    "ARTIFACT_ANTAGONIST",
    "ARTIFACT_MODEL",
    "ARTIFACT_MODEL_BASE",
    "ARTIFACT_MODEL_DIE",
    "ARTIFACT_SPLINT",
    "ARTIFACT_TOOTH",
    "ARTIFACT_UNKNOWN",
    "ArtifactClassification",
    "StructureResolution",
    "ThicknessStats",
    "STRUCTURE_HOLLOW",
    "STRUCTURE_REVIEW",
    "STRUCTURE_SOLID",
    "WORKFLOW_MANUAL_REVIEW",
    "WORKFLOW_ORTHO_IMPLANT",
    "WORKFLOW_ORTHO_TOOTH",
    "WORKFLOW_SPLINT",
    "WORKFLOW_STANDARD",
    "WORKFLOW_TOOTH_MODEL",
    "classify_artifact",
    "extract_case_id",
    "measure_mesh_thickness_stats",
    "resolve_ortho_structure",
]
