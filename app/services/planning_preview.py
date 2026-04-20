"""Read-only planning preview: maps ClassificationRow data to predicted job name
and case grouping without executing any prep or dispatch."""
from __future__ import annotations

from ..schemas import BatchPlanPreviewResponse, ClassificationRow, PlanPreviewRow

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
    preview_rows = [build_row_preview(r) for r in rows]
    groups = {r.predicted_group_key for r in preview_rows if r.predicted_group_key}
    cannot_fit_count = sum(1 for r in preview_rows if r.cannot_fit)
    return BatchPlanPreviewResponse(
        rows=preview_rows,
        group_count=len(groups),
        cannot_fit_count=cannot_fit_count,
    )
