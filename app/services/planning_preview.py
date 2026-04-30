"""Read-only planning preview: maps ClassificationRow data to predicted job name
and case grouping without executing any prep or dispatch."""
from __future__ import annotations

import hashlib

from ..schemas import (
    BatchPlanPreviewResponse,
    BuildManifest,
    ClassificationRow,
    PlanPreviewRow,
    PreviewBatchGroup,
    PreviewBatchesResponse,
)
from .build_planning import plan_build_manifests

_MODEL_TYPE_TO_ARTIFACT: dict[str, str] = {
    "Ortho - Solid": "ortho_solid",
    "Ortho - Hollow": "ortho_hollow",
    "Die": "die",
    "Tooth": "tooth",
    "Splint": "splint",
}


def _predict_job_name(row: ClassificationRow) -> str | None:
    if not row.case_id or not row.model_type:
        return None
    artifact_type = _MODEL_TYPE_TO_ARTIFACT.get(row.model_type, row.model_type.lower())
    return f"{row.case_id}_{artifact_type}"


def _group_key(row: ClassificationRow) -> str | None:
    return row.case_id or None


def build_row_preview(row: ClassificationRow) -> PlanPreviewRow:
    preview_available = bool(row.model_type and row.preset and row.status != "Needs Review")
    return PlanPreviewRow(
        row_id=row.row_id,
        file_name=row.file_name,
        case_id=row.case_id,
        model_type=row.model_type,
        preset=row.preset,
        predicted_job_name=_predict_job_name(row) if preview_available else None,
        predicted_group_key=_group_key(row),
        cannot_fit=False,
        cannot_fit_reason=None,
        preview_available=preview_available,
    )


def build_batch_preview(rows: list[ClassificationRow]) -> BatchPlanPreviewResponse:
    row_by_id = {row.row_id: row for row in rows if row.row_id is not None}
    preview_by_row_id: dict[int, PlanPreviewRow] = {}
    planned_group_count = 0

    for manifest in plan_build_manifests(rows):
        if manifest.planning_status == "planned":
            planned_group_count += 1
            for group in manifest.import_groups:
                for file_spec in group.files:
                    row = row_by_id.get(file_spec.row_id)
                    if row is None:
                        continue
                    preview_by_row_id[file_spec.row_id] = PlanPreviewRow(
                        row_id=file_spec.row_id,
                        file_name=row.file_name,
                        case_id=row.case_id,
                        model_type=row.model_type,
                        preset=row.preset,
                        predicted_job_name=None,
                        predicted_group_key=manifest.compatibility_key,
                        cannot_fit=False,
                        cannot_fit_reason=None,
                        preview_available=True,
                    )
            continue

        reason = (
            f"Build planning requires manual review: {manifest.non_plannable_reason}"
        )
        for row in rows:
            if row.row_id is None or row.case_id not in manifest.case_ids:
                continue
            preview_by_row_id[row.row_id] = PlanPreviewRow(
                row_id=row.row_id,
                file_name=row.file_name,
                case_id=row.case_id,
                model_type=row.model_type,
                preset=row.preset,
                predicted_job_name=None,
                predicted_group_key=manifest.compatibility_key,
                cannot_fit=True,
                cannot_fit_reason=reason,
                preview_available=False,
            )

    preview_rows = [
        preview_by_row_id[row.row_id]
        if row.row_id is not None and row.row_id in preview_by_row_id
        else build_row_preview(row)
        for row in rows
    ]
    cannot_fit_count = sum(row.cannot_fit for row in preview_rows)
    return BatchPlanPreviewResponse(
        rows=preview_rows,
        group_count=planned_group_count,
        cannot_fit_count=cannot_fit_count,
    )


def manifest_row_ids(manifest: BuildManifest, rows: list[ClassificationRow]) -> list[int]:
    row_ids: list[int] = []
    for group in manifest.import_groups:
        for file_spec in group.files:
            row_ids.append(file_spec.row_id)
    if row_ids:
        return sorted(set(row_ids))

    case_ids = set(manifest.case_ids)
    return sorted(
        row.row_id
        for row in rows
        if row.row_id is not None and row.case_id in case_ids
    )


def build_manifest_assignment_id(manifest: BuildManifest, row_ids: list[int]) -> str:
    digest = hashlib.sha256(
        ",".join(str(row_id) for row_id in sorted(row_ids)).encode("utf-8")
    ).hexdigest()[:16]
    compatibility_key = manifest.compatibility_key or "non-plannable"
    return f"{compatibility_key}|{digest}"


def build_preview_batches(rows: list[ClassificationRow]) -> PreviewBatchesResponse:
    groups: list[PreviewBatchGroup] = []
    for manifest in plan_build_manifests(rows):
        row_ids = manifest_row_ids(manifest, rows)
        groups.append(
            PreviewBatchGroup(
                manifest_id=build_manifest_assignment_id(manifest, row_ids),
                row_ids=row_ids,
                case_ids=manifest.case_ids,
                compatibility_key=manifest.compatibility_key,
                printer_model=manifest.printer_group,
                material_label=manifest.material_label,
                layer_height_microns=(
                    int(manifest.layer_thickness_mm * 1000)
                    if manifest.layer_thickness_mm is not None
                    else None
                ),
                planning_status=manifest.planning_status,
                non_plannable_reason=manifest.non_plannable_reason,
            )
        )
    return PreviewBatchesResponse(groups=groups)
