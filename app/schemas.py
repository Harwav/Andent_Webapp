from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Phase0ModelType = Literal["Ortho - Solid", "Ortho - Hollow", "Die", "Tooth", "Splint"]
ConfidenceLevel = Literal["high", "medium", "low"]


class DimensionSummary(BaseModel):
    x_mm: float
    y_mm: float
    z_mm: float


class ClassificationRow(BaseModel):
    row_id: int | None = None
    file_name: str
    case_id: str | None = None
    model_type: Phase0ModelType | None = None
    preset: str | None = None
    confidence: ConfidenceLevel
    status: str
    dimensions: DimensionSummary | None = None
    volume_ml: float | None = None
    structure: str | None = None
    structure_confidence: ConfidenceLevel | None = None
    structure_reason: str | None = None
    structure_metrics: dict[str, Any] | None = None
    structure_locked: bool = False
    review_required: bool = False
    review_reason: str | None = None
    current_event_at: str | None = None
    created_at: str | None = None
    printer: str | None = None
    person: str | None = None
    thumbnail_url: str | None = None
    file_url: str | None = None


class UploadClassificationResponse(BaseModel):
    file_count: int
    rows: list[ClassificationRow]


class QueueSnapshotResponse(BaseModel):
    active_rows: list[ClassificationRow]
    processed_rows: list[ClassificationRow]


class UpdateClassificationRowRequest(BaseModel):
    model_type: Phase0ModelType | None = None
    preset: str | None = None


class RowIdsRequest(BaseModel):
    row_ids: list[int] = Field(default_factory=list, min_length=1)


class BulkUpdateClassificationRowsRequest(RowIdsRequest):
    model_type: Phase0ModelType | None = None
    preset: str | None = None


class BulkDeleteRowsResponse(BaseModel):
    deleted_row_ids: list[int]


class PlanPreviewRow(BaseModel):
    row_id: int
    file_name: str
    case_id: str | None
    model_type: str | None
    preset: str | None
    predicted_job_name: str | None
    predicted_group_key: str | None
    cannot_fit: bool
    cannot_fit_reason: str | None
    preview_available: bool


class BatchPlanPreviewResponse(BaseModel):
    rows: list[PlanPreviewRow]
    group_count: int
    cannot_fit_count: int
