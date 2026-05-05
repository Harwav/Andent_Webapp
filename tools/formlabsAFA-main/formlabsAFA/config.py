from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]


BuildMode = Literal["frame", "loose", "webbing"]


class BuildConfig(BaseModel):
    mode: BuildMode = "frame"


class GeneralConfig(BaseModel):
    base_path: Path
    preform_server_path: str = ""
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    debug: bool = False


class PrinterConfig(BaseModel):
    serial_or_group_queue_id: str = ""
    dashboard_username: str = ""
    dashboard_password: str = ""
    upload_to_printer: bool = True
    backup_printer_list: list[str] = []


class PreFormServerConfig(BaseModel):
    host: str = "localhost"
    port: int = 44388
    connection_timeout_seconds: int = 10


class MaterialConfig(BaseModel):
    layer_thickness_mm: float = 0.16
    machine_type: str = "FRML-4-0"
    material_code: str = "FLFMGR01"
    print_setting: str | None = None
    fps_file: str | None = None

    def to_payload(self) -> dict:
        if self.fps_file:
            return {"fps_file": self.fps_file}
        payload: dict = {
            "layer_thickness_mm": self.layer_thickness_mm,
            "machine_type": self.machine_type,
            "material_code": self.material_code,
        }
        # Only include print_setting if explicitly set. Omitting it lets PreForm
        # pick the preset implied by (machine_type, material_code, layer_thickness_mm)
        # — e.g. the "fast model" preset for FRML-4-0 + FLFMGR01 + 0.16mm.
        if self.print_setting:
            payload["print_setting"] = self.print_setting
        return payload


class BatchConfig(BaseModel):
    initial_batch_size: int = 20
    min_models: int = 12
    process_partial_batches: bool = True
    delay_between_checks_seconds: float = 2.0
    n_parallel_batches: int = 5


class HollowingConfig(BaseModel):
    enabled: bool = True
    honeycomb_infill: bool = True
    shell_thickness_mm: float = 2.0
    hex_wall_thickness_mm: float = 1.0
    cutoff_height_mm: float = 0.01
    extrude_distance_mm: float = 0.11


class DrainHoleConfig(BaseModel):
    radius_mm: float = 1.0
    height_ratio: float = 0.75
    suppression_distance_mm: float = 5.0
    max_count: int = 5
    # Retry params — used when a model produces cups on the first attempt.
    # Relaxed values give the drain-hole algorithm more room to find valid placements.
    retry_suppression_distance_mm: float = 2.0
    retry_height_ratio: float = 0.95
    retry_radius_mm: float = 0.75


class ChamferConfig(BaseModel):
    enabled: bool = False
    leg_depth_mm: float = 0.01
    height_mm: float = 0.01


class LayoutBounds(BaseModel):
    x_min_mm: float = -169.016
    x_max_mm: float = 169.015
    y_min_mm: float = -92.0
    y_max_mm: float = 97.0


class LayoutConfig(BaseModel):
    """Mode-agnostic layout settings."""

    model_spacing_mm: float = 1.0


class FreeLayoutConfig(BaseModel):
    """Used by loose and webbing modes. Frame mode uses profile-specific bounds."""

    bounds: LayoutBounds = LayoutBounds()


class TabsConfig(BaseModel):
    """Tab geometry — shared by frame-punch and webbing beams."""

    height_mm: float = 1.6
    frame_connection_distance_mm: float = 3.99  # frame-mode erosion distance


class BreakawayConfig(BaseModel):
    enabled: bool = True
    width_mm: float = 1.0
    height_mm: float = 0.8


class FrameConfig(BaseModel):
    """Frame-mode-only configuration."""

    profiles_dir: str = "frame_profiles"
    large_frame_cutoff: int = 15
    min_large_models_small_frame: int = 4
    front_clearance_mm: float = 4.0
    back_clearance_mm: float = 4.0
    large_model_min_y_dim_mm: float = 55.0


class WebbingConfig(BaseModel):
    """Webbing-mode-only configuration. Beam height comes from [tabs].height_mm."""

    thickness_mm: float = 2.0
    chamfer_mm: float = 0.5
    perimeter_rail: bool = True
    connect_front: bool = True
    connect_back: bool = False
    connect_left: bool = True
    connect_right: bool = True
    max_span_mm: float = 60.0
    punch_offset_mm: float = 0.0
    anti_cup_min_span_mm: float = 15.0
    anti_cup_spacing_mm: float = 10.0
    anti_cup_width_mm: float = 3.0
    anti_cup_height_mm: float = 0.6


class FixtureConfig(BaseModel):
    enabled: bool = False
    stl_path: str = ""


class ModelLabelConfig(BaseModel):
    """Per-model patient-ID labels etched into each aligner via PreForm's add_label.

    Label placement is user-configured because aligner geometry varies. Position
    is computed per-model as:
        world_pos = model.position + bbox_min + bbox_size * bbox_fraction + offset_mm

    Label text is derived from the filename's human-readable portion.
    Any label failure fails the whole batch (traceability is load-bearing).
    """

    enabled: bool = False
    font_size_mm: float = 3.0
    depth_mm: float = 0.4
    # Fraction of the model's bounding box, 0..1 per axis.
    # Default: posterior/right/occlusal. TUNE FOR YOUR ALIGNER GEOMETRY.
    bbox_fraction: list[float] = Field(default_factory=lambda: [0.9, 1.0, 1.0])
    offset_mm: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    orientation_deg: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])

    @model_validator(mode="after")
    def _validate_vectors(self) -> ModelLabelConfig:
        for name, vec in (
            ("bbox_fraction", self.bbox_fraction),
            ("offset_mm", self.offset_mm),
            ("orientation_deg", self.orientation_deg),
        ):
            if len(vec) != 3:
                raise ValueError(f"model_labels.{name} must have exactly 3 entries")
        for v in self.bbox_fraction:
            if not 0.0 <= v <= 1.0:
                raise ValueError(
                    "model_labels.bbox_fraction entries must each be in [0, 1]"
                )
        return self


class SupportConfig(BaseModel):
    support_all_minima: bool = False


class DashboardApiConfig(BaseModel):
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    poll_interval_seconds: float = 30.0


class AppConfig(BaseModel):
    general: GeneralConfig
    build: BuildConfig = BuildConfig()
    printer: PrinterConfig = PrinterConfig()
    preform_server: PreFormServerConfig = PreFormServerConfig()
    material: MaterialConfig = MaterialConfig()
    batch: BatchConfig = BatchConfig()
    hollowing: HollowingConfig = HollowingConfig()
    drain_holes: DrainHoleConfig = DrainHoleConfig()
    chamfer: ChamferConfig = ChamferConfig()
    layout: LayoutConfig = LayoutConfig()
    free_layout: FreeLayoutConfig = FreeLayoutConfig()
    tabs: TabsConfig = TabsConfig()
    breakaway: BreakawayConfig = BreakawayConfig()
    frame: FrameConfig = FrameConfig()
    webbing: WebbingConfig = WebbingConfig()
    fixture: FixtureConfig = FixtureConfig()
    model_labels: ModelLabelConfig = ModelLabelConfig()
    support: SupportConfig = SupportConfig()
    dashboard_api: DashboardApiConfig = DashboardApiConfig()

    @model_validator(mode="after")
    def _validate_combos(self) -> AppConfig:
        # Batch sizing sanity — min_models > initial_batch_size causes infinite requeue.
        if self.batch.min_models > self.batch.initial_batch_size:
            raise ValueError(
                f"batch.min_models ({self.batch.min_models}) cannot exceed "
                f"batch.initial_batch_size ({self.batch.initial_batch_size}) — "
                f"batches would never reach min_models and requeue forever"
            )

        # Webbing mode requires at least one beam source, or the batch has no structure.
        if self.build.mode == "webbing":
            w = self.webbing
            has_beams = (
                w.connect_front
                or w.connect_back
                or w.connect_left
                or w.connect_right
                or w.perimeter_rail
            )
            if not has_beams:
                raise ValueError(
                    "build.mode='webbing' but no beams would be generated — "
                    "set at least one of webbing.connect_{front,back,left,right} "
                    "or webbing.perimeter_rail to true"
                )

        # Fixture path must be set if fixture is enabled. (File-existence is
        # checked at startup in __main__ where I/O belongs.)
        if self.fixture.enabled and not self.fixture.stl_path:
            raise ValueError(
                "fixture.enabled=true but fixture.stl_path is empty"
            )

        return self


def load_config(path: Path) -> AppConfig:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return AppConfig.model_validate(data)
