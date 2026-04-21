from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Phase0ModelType = Literal["Ortho - Solid", "Ortho - Hollow", "Die", "Tooth", "Splint"]
ConfidenceLevel = Literal["high", "medium", "low"]
BuildPlanningStatus = Literal["planned", "non_plannable"]
NonPlannableReason = Literal[
    "oversized_case",
    "incompatible_case_presets",
    "missing_dimensions",
    "missing_file_path",
    "missing_row_id",
]


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
    file_path: str | None = Field(default=None, exclude=True)


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


class FilePrepSpec(BaseModel):
    row_id: int
    case_id: str
    file_name: str
    file_path: str
    preset_name: str
    compatibility_key: str
    xy_footprint_estimate: float
    support_inflation_factor: float
    order: int = 0
    preform_hint: str | None = None


class BuildManifestImportGroup(BaseModel):
    preset_name: str
    preform_hint: str | None = None
    row_ids: list[int] = Field(default_factory=list)
    files: list[FilePrepSpec] = Field(default_factory=list)


class CasePackProfile(BaseModel):
    case_id: str
    compatibility_key: str
    file_specs: list[FilePrepSpec] = Field(default_factory=list)
    total_xy_footprint: float
    difficulty_score: float
    file_count: int


class BuildCandidate(BaseModel):
    compatibility_key: str
    case_ids: list[str] = Field(default_factory=list)
    used_xy_budget: float = 0.0
    remaining_xy_budget: float = 0.0


class BuildManifest(BaseModel):
    compatibility_key: str | None
    case_ids: list[str] = Field(default_factory=list)
    preset_names: list[str] = Field(default_factory=list)
    import_groups: list[BuildManifestImportGroup] = Field(default_factory=list)
    planning_status: BuildPlanningStatus = "planned"
    non_plannable_reason: NonPlannableReason | None = None


PrintJobStatus = Literal["Queued", "Printing", "Failed", "Paused", "Completed"]


class PrintJob(BaseModel):
    """Print job schema for the print queue.
    
    Represents a print job submitted to PreFormServer and tracked
    via the Formlabs Web API.
    """
    id: int | None = None
    job_name: str = Field(pattern=r"^\d{6}-\d{3}$")  # YYMMDD-001 format
    scene_id: str | None = None  # From PreFormServer
    print_job_id: str | None = None  # From Formlabs API
    status: PrintJobStatus = "Queued"
    preset: str
    case_ids: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    screenshot_url: str | None = None
    printer_type: str | None = None
    resin: str | None = None
    layer_height_microns: int | None = None
    estimated_completion: str | None = None
    error_message: str | None = None


class PrintJobListResponse(BaseModel):
    jobs: list[PrintJob]
    total_count: int
