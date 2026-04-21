"""Read-only planning preview: maps ClassificationRow data to predicted job name
and case grouping without executing any prep or dispatch."""
from __future__ import annotations

from ..schemas import BatchPlanPreviewResponse, ClassificationRow, PlanPreviewRow
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
