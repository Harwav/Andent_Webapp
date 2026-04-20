# andent_service_pipeline.py
"""
Headless preparation pipeline — GUI-free orchestration extracted from ProcessingController.
All GUI callbacks are routed through PipelineEventHandler so the pipeline can run
from the web service (WebEventHandler), desktop (TkinterEventHandler), or tests (NullEventHandler).
"""
from __future__ import annotations

import copy
import json
import logging
import os
import queue
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from typing import Protocol, runtime_checkable

from .fps_parser import FPSParser
from .andent_planning import (
    BuildPlan,
    ManualReviewItem,
    ResolvedWorkflowPolicy,
    STANDARD_WORKFLOW_MODE,
    WORKFLOW_ORTHO_TOOTH,
    WORKFLOW_STANDARD,
    WORKFLOW_SPLINT,
    WORKFLOW_TOOTH_MODEL,
    _CaseCandidate,
    is_andent_v2_workflow_mode,
    plan_andent_builds,
)
from .constants import (
    MAX_FILENAME_LENGTH,
    MAX_PATH_LENGTH,
    LICENSE_FEATURE_FORM_EXPORT,
    LICENSE_FEATURE_HOLLOWING,
    LICENSE_FEATURE_AUTO_SUPPORT,
    LICENSE_FEATURE_ADVANCED_STATS,
    BUILD_PLATES,
    DEFAULT_BUILD_PLATE,
    PACKING_EFFICIENCY,
    MAX_BATCH_SIZE_CAP,
    BATCH_IMPORT_LIMIT,
    ENABLE_BATCH_IMPORT,
)
from .stl_validator import validate_stl_batch, ValidationStatus
from .batch_optimizer import BatchOptimizer, get_build_plate_for_printer


HOLLOW_ONLY_SCAN_PARAMS = {
    "shell_thickness_mm",
    "wall_thickness_mm",
    "drain_hole_radius_mm",
    "drain_hole_height_ratio",
}


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = "".join(c for c in name if c.isprintable())
    name = name.strip(" .")
    name = name[: MAX_FILENAME_LENGTH - 10]
    return name if name else "unnamed_job"


# ---------------------------------------------------------------------------
# Event handler protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class PipelineEventHandler(Protocol):
    def update_status(self, status: str) -> None: ...
    def show_error(self, title: str, msg: str) -> None: ...
    def show_warning(self, title: str, msg: str) -> None: ...
    def set_stage(self, stage: str) -> None: ...
    def reset_batch_progress(self, count: int) -> None: ...
    def set_batch_progress_value(self, val: int) -> None: ...
    def update_overall_progress(self, count: int) -> None: ...
    def processing_finished(self, processed: int, resin_saved: float, skipped: list, review_count: int = 0) -> None: ...
    def show_stages(self, **kwargs) -> None: ...
    def add_result_to_list(self, result_data: dict) -> None: ...
    def update_latest_result(self, result_data: dict) -> None: ...
    def record_batch_completion(self, successful: int, resin_saved: float) -> None: ...
    def update_folder_status(self, folder_path: str, status: str) -> None: ...
    def show_validation_dialog(self, validation: dict) -> str: ...
    def complete_stages(self) -> None: ...
    def hide_stages(self) -> None: ...
    def auto_save_detailed_report(self, rows: list, name: str) -> None: ...


class NullEventHandler:
    """No-op handler for headless / test execution."""

    def update_status(self, status: str) -> None:
        logging.debug("pipeline: %s", status)

    def show_error(self, title: str, msg: str) -> None:
        logging.error("pipeline error [%s]: %s", title, msg)

    def show_warning(self, title: str, msg: str) -> None:
        logging.warning("pipeline warning [%s]: %s", title, msg)

    def set_stage(self, stage: str) -> None:
        logging.debug("stage: %s", stage)

    def reset_batch_progress(self, count: int) -> None:
        pass

    def set_batch_progress_value(self, val: int) -> None:
        pass

    def update_overall_progress(self, count: int) -> None:
        pass

    def processing_finished(self, processed: int, resin_saved: float, skipped: list, review_count: int = 0) -> None:
        logging.info(
            "pipeline finished: processed=%d resin_saved=%.2f skipped=%d review=%d",
            processed,
            resin_saved,
            len(skipped),
            review_count,
        )

    def show_stages(self, **kwargs) -> None:
        pass

    def add_result_to_list(self, result_data: dict) -> None:
        pass

    def update_latest_result(self, result_data: dict) -> None:
        pass

    def record_batch_completion(self, successful: int, resin_saved: float) -> None:
        pass

    def update_folder_status(self, folder_path: str, status: str) -> None:
        logging.debug("folder [%s]: %s", folder_path, status)

    def show_validation_dialog(self, validation: dict) -> str:
        return "continue"

    def complete_stages(self) -> None:
        pass

    def hide_stages(self) -> None:
        pass

    def auto_save_detailed_report(self, rows: list, name: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Job config and result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PipelineJobConfig:
    folders_to_process: List[str]
    api_payload: Dict[str, Any]
    print_settings_for_manifest: Dict[str, Any]
    selected_printer_ids: List[str]
    save_only: bool = False
    save_form_files: bool = False


@dataclass
class PipelineResult:
    processed_count: int
    resin_saved_ml: float
    skipped_files: List[str]
    manual_review_items: List[Any]
    artifact_paths: List[str] = field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Headless pipeline (all domain logic, no Tkinter)
# ---------------------------------------------------------------------------

class HeadlessPipeline:
    """
    GUI-free prep orchestrator.
    All self.gui.* calls from the original ProcessingController are routed
    through self._events (a PipelineEventHandler).
    """

    def __init__(
        self,
        settings_manager,
        api_client,
        event_handler: PipelineEventHandler,
        local_controller,
        license_manager=None,
    ):
        self.settings = settings_manager
        self.api = api_client
        self._events = event_handler
        self.local_controller = local_controller
        self.license_manager = license_manager
        self.skipped_files: List[str] = []
        self.current_scene_id: Optional[str] = None
        self.manual_review_items: List[ManualReviewItem] = []
        self.manual_review_report_path: Optional[str] = None

        # OPT-10: Async report generation queue
        self._report_queue: queue.Queue = queue.Queue()
        self._report_thread: Optional[threading.Thread] = None
        self._report_thread_running = False

        # OPT-3: Scene pre-creation for faster batch transitions
        self._precreation_executor: Optional[ThreadPoolExecutor] = None
        self._precreation_future = None
        self._precreated_scene_id: Optional[str] = None

        # Result tracking set by _run_processing_loop for run() to return
        self._last_processed_count: int = 0
        self._last_resin_saved: float = 0.0

    def run(self, job: PipelineJobConfig) -> PipelineResult:
        """Entry point for headless execution."""
        self._run_processing_loop(
            folders_to_process=job.folders_to_process,
            api_payload=job.api_payload,
            print_settings_for_manifest=job.print_settings_for_manifest,
            selected_printer_ids=job.selected_printer_ids,
            pause_evt=threading.Event(),
            cancel_evt=threading.Event(),
            save_only=job.save_only,
            save_form_files=job.save_form_files,
        )
        return PipelineResult(
            processed_count=self._last_processed_count,
            resin_saved_ml=self._last_resin_saved,
            skipped_files=list(self.skipped_files),
            manual_review_items=list(self.manual_review_items),
        )

    # ------------------------------------------------------------------
    # Scene pre-creation (OPT-3)
    # ------------------------------------------------------------------

    def _init_precreation_executor(self):
        if self._precreation_executor is None:
            self._precreation_executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="ScenePreCreate"
            )

    def _precreate_scene(self, api_payload: dict) -> Optional[str]:
        try:
            scene_id, err = self.api.create_scene(api_payload)
            if err:
                logging.debug("OPT-3: Scene pre-creation failed: %s", err)
                return None
            logging.info("OPT-3: Pre-created scene: %s", scene_id)
            return scene_id
        except Exception as e:
            logging.debug("OPT-3: Scene pre-creation exception: %s", e)
            return None

    def _start_scene_precreation(self, api_payload: dict, batch_num: int, total_batches: int):
        if batch_num >= total_batches:
            return
        self._init_precreation_executor()
        self._precreation_future = self._precreation_executor.submit(
            self._precreate_scene, api_payload
        )
        logging.debug("OPT-3: Started pre-creating scene for batch %d", batch_num + 1)

    def _get_precreated_scene(self) -> Optional[str]:
        if self._precreation_future is None:
            return None
        try:
            scene_id = self._precreation_future.result(timeout=0.5)
            self._precreation_future = None
            if scene_id:
                logging.info("OPT-3: Using pre-created scene: %s", scene_id)
            return scene_id
        except Exception as e:
            logging.debug("OPT-3: Pre-created scene not available: %s", e)
            self._precreation_future = None
            return None

    def _cleanup_precreation(self):
        if self._precreation_executor is not None:
            self._precreation_executor.shutdown(wait=False)
            self._precreation_executor = None
            self._precreation_future = None

    # ------------------------------------------------------------------
    # Async report worker (OPT-10)
    # ------------------------------------------------------------------

    def _start_report_worker(self):
        if self._report_thread is not None and self._report_thread.is_alive():
            return
        self._report_thread_running = True
        self._report_thread = threading.Thread(
            target=self._report_worker, name="ReportWorker", daemon=True
        )
        self._report_thread.start()
        logging.debug("OPT-10: Started async report worker thread")

    def _stop_report_worker(self):
        if self._report_thread is None:
            return
        self._report_thread_running = False
        self._report_queue.put(None)
        self._report_thread.join(timeout=10.0)
        if self._report_thread.is_alive():
            logging.warning("OPT-10: Report worker thread did not stop cleanly")
        self._report_thread = None
        logging.debug("OPT-10: Stopped async report worker thread")

    def _report_worker(self):
        while self._report_thread_running:
            try:
                task = self._report_queue.get(timeout=0.1)
                if task is None:
                    break
                try:
                    self._generate_reports_sync(*task)
                except Exception as e:
                    logging.error("OPT-10: Error generating report: %s", e)
                finally:
                    self._report_queue.task_done()
            except queue.Empty:
                continue
        logging.debug("OPT-10: Report worker exiting")

    # ------------------------------------------------------------------
    # Async form export worker (OPT-2)
    # ------------------------------------------------------------------

    def _init_form_export_queue(self):
        if not hasattr(self, "_form_export_queue"):
            self._form_export_queue: queue.Queue = queue.Queue()
            self._form_export_thread: Optional[threading.Thread] = None
            self._form_export_errors: List[str] = []
            self._form_export_running = False
            self._form_exports_queued = 0
            self._form_exports_completed = 0
            self._form_exports_in_progress: Optional[str] = None
            self._form_export_total_duration_s = 0.0
            self._form_export_max_duration_s = 0.0
            self._show_export_status = False

    def _start_form_export_worker(self):
        self._init_form_export_queue()
        if self._form_export_thread is not None and self._form_export_thread.is_alive():
            return
        self._form_export_errors = []
        self._form_exports_queued = 0
        self._form_exports_completed = 0
        self._form_exports_in_progress = None
        self._form_export_total_duration_s = 0.0
        self._form_export_max_duration_s = 0.0
        self._show_export_status = False
        self._form_export_running = True
        self._form_export_thread = threading.Thread(
            target=self._form_export_worker, name="FormExporter", daemon=True
        )
        self._form_export_thread.start()
        logging.debug("OPT-2: Started async form export worker thread")

    def _update_form_export_status(self):
        self._init_form_export_queue()
        total = self._form_exports_queued
        completed = self._form_exports_completed
        if total <= 0 or not self._show_export_status:
            return
        if self._form_exports_in_progress:
            status = (
                f"Exporting .form files ({completed}/{total} complete): "
                f"{self._form_exports_in_progress}"
            )
        else:
            status = f"Exporting .form files ({completed}/{total} complete)..."
        self._events.update_status(status)

    def _form_export_worker(self):
        while self._form_export_running:
            try:
                item = self._form_export_queue.get(timeout=1.0)
                if item is None:
                    self._form_export_queue.task_done()
                    break
                scene_id, job_name, output_folder, batch_num, cleanup_after_export = item
                try:
                    form_filename = f"{job_name}.form"
                    form_filepath = os.path.join(output_folder, form_filename)
                    if len(form_filepath) > MAX_PATH_LENGTH:
                        form_filename = form_filename[:50] + ".form"
                        form_filepath = os.path.join(output_folder, form_filename)
                    self._form_exports_in_progress = form_filename
                    self._update_form_export_status()
                    export_start_time = time.perf_counter()
                    logging.info("OPT-2: Saving form file in background: %s", form_filename)
                    save_ok, save_err = self.api.save_scene(
                        scene_id, form_filepath, threading.Event(), threading.Event()
                    )
                    export_duration_s = time.perf_counter() - export_start_time
                    self._form_export_total_duration_s += export_duration_s
                    self._form_export_max_duration_s = max(
                        self._form_export_max_duration_s, export_duration_s
                    )
                    if save_ok:
                        logging.info(
                            "OPT-2: Form export completed: %s in %.2fs",
                            form_filename,
                            export_duration_s,
                        )
                    else:
                        error_msg = f"Batch {batch_num}: {save_err} (after {export_duration_s:.2f}s)"
                        self._form_export_errors.append(error_msg)
                        logging.warning("OPT-2: Form export failed: %s", error_msg)
                except Exception as e:
                    error_msg = f"Batch {batch_num}: {e}"
                    self._form_export_errors.append(error_msg)
                    logging.error("OPT-2: Form export error: %s", error_msg)
                finally:
                    if cleanup_after_export and scene_id:
                        try:
                            self._cleanup_scene(scene_id)
                        except Exception as cleanup_error:
                            logging.error(
                                "OPT-2: Failed to cleanup exported scene %s: %s",
                                scene_id,
                                cleanup_error,
                            )
                    self._form_exports_completed += 1
                    self._form_exports_in_progress = None
                    self._update_form_export_status()
                    self._form_export_queue.task_done()
            except queue.Empty:
                continue
        logging.debug("OPT-2: Form export worker exiting")

    def _queue_form_export(
        self, scene_id: str, job_name: str, batch_num: int, cleanup_after_export: bool = True
    ):
        self._init_form_export_queue()
        output_folder = self.settings.get("output")
        os.makedirs(output_folder, exist_ok=True)
        self._form_export_queue.put(
            (scene_id, job_name, output_folder, batch_num, cleanup_after_export)
        )
        self._form_exports_queued += 1
        self._update_form_export_status()
        logging.debug("OPT-2: Queued form export for batch #%d", batch_num)

    def _wait_for_form_exports(self, timeout: float = 300.0):
        self._init_form_export_queue()
        if self._form_export_thread is None:
            return
        self._show_export_status = True
        self._update_form_export_status()
        self._form_export_queue.put(None)
        try:
            join_thread = threading.Thread(
                target=self._form_export_queue.join, daemon=True
            )
            join_thread.start()
            join_thread.join(timeout=timeout)
            if join_thread.is_alive():
                logging.warning(
                    "OPT-2: Form export wait timed out after %ss", timeout
                )
        except Exception as e:
            logging.warning("OPT-2: Error waiting for form exports: %s", e)
        if self._form_export_thread.is_alive():
            self._form_export_running = False
            self._form_export_thread.join(timeout=10.0)
            if self._form_export_thread.is_alive():
                logging.warning("OPT-2: Form export worker did not stop cleanly")
        self._form_export_thread = None
        self._form_exports_in_progress = None
        self._update_form_export_status()
        self._show_export_status = False
        if self._form_export_errors:
            logging.warning("OPT-2: Form export errors: %s", self._form_export_errors)
            joined_errors = "\n".join(self._form_export_errors[:5])
            if len(self._form_export_errors) > 5:
                joined_errors += f"\n...and {len(self._form_export_errors) - 5} more"
            self._events.show_warning(
                "Form Export Warning", f"Some .form exports failed:\n{joined_errors}"
            )
        completed_exports = max(self._form_exports_completed, 0)
        if completed_exports > 0:
            avg_duration_s = self._form_export_total_duration_s / completed_exports
            logging.info(
                "OPT-2: Form export timing summary: %s file(s), avg %.2fs, max %.2fs, total %.2fs",
                completed_exports,
                avg_duration_s,
                self._form_export_max_duration_s,
                self._form_export_total_duration_s,
            )
        logging.debug("OPT-2: Stopped async form export worker")

    # ------------------------------------------------------------------
    # Policy / settings helpers
    # ------------------------------------------------------------------

    def _can_use_feature(self, feature_name: str) -> bool:
        if not self.license_manager:
            return False
        return self.license_manager.has_feature(feature_name)

    def _get_workflow_mode(self) -> str:
        return self.settings.get("workflow_mode") or STANDARD_WORKFLOW_MODE

    def _is_andent_v2_mode(self) -> bool:
        return is_andent_v2_workflow_mode(self._get_workflow_mode())

    def _auto_dispatch_real_printers_enabled(self) -> bool:
        return bool(self.settings.get("andent_v2_auto_dispatch_real_printers"))

    def _build_default_policy(self, approval_only: bool) -> ResolvedWorkflowPolicy:
        return ResolvedWorkflowPolicy(
            workflow=WORKFLOW_STANDARD,
            display_name="Standard",
            approval_only=approval_only,
            build_family=WORKFLOW_STANDARD,
        )

    def _resolve_api_params_for_policy(self, policy: ResolvedWorkflowPolicy) -> Dict:
        api_params = dict(self.settings.get("api_params") or {})
        if policy.api_params_override:
            api_params.update(policy.api_params_override)
        if api_params.get("hollow") is False:
            for key in HOLLOW_ONLY_SCAN_PARAMS:
                api_params.pop(key, None)
        return api_params

    def _resolve_scene_payload_for_policy(
        self,
        api_payload: Dict,
        print_settings_for_manifest: Dict,
        policy: ResolvedWorkflowPolicy,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        payload = dict(api_payload)
        payload, policy_error = self._resolve_required_scene_payload_for_policy(
            payload, print_settings_for_manifest, policy
        )
        if policy_error:
            return None, policy_error
        if not policy.scene_payload_override:
            return payload, None
        if "fps_file" in payload:
            scene_settings, error = FPSParser.parse_fps_file(payload["fps_file"])
            if error or not scene_settings:
                return None, "Could not parse the FPS file to verify workflow-specific scene settings."
            for key, expected in policy.scene_payload_override.items():
                actual = scene_settings.get(key)
                if actual != expected:
                    return None, (
                        f"FPS scene setting '{key}' is {actual!r}, but workflow requires {expected!r}."
                    )
            return payload, None
        payload.update(policy.scene_payload_override)
        return payload, None

    def _resolve_required_scene_payload_for_policy(
        self,
        payload: Dict,
        print_settings_for_manifest: Dict,
        policy: ResolvedWorkflowPolicy,
    ) -> Tuple[Dict, Optional[str]]:
        if not policy.required_material_label and policy.required_layer_thickness_mm is None:
            return payload, None
        required_scene_settings, error = self._find_required_scene_settings_for_policy(
            print_settings_for_manifest, payload, policy
        )
        if error:
            return payload, error
        if "fps_file" in payload:
            fps_scene_settings, parse_error = FPSParser.parse_fps_file(payload["fps_file"])
            if parse_error or not fps_scene_settings:
                return payload, "Could not parse the FPS file to verify required splint print settings."
            for key in ("machine_type", "material_code", "print_setting", "layer_thickness_mm"):
                if fps_scene_settings.get(key) != required_scene_settings.get(key):
                    return payload, (
                        f"Splint FPS settings do not match {self._format_required_profile(policy)}."
                    )
            return payload, None
        resolved_payload = dict(payload)
        resolved_payload.update(required_scene_settings)
        return resolved_payload, None

    def _format_required_profile(self, policy: ResolvedWorkflowPolicy) -> str:
        material = policy.required_material_label or "the required material"
        if policy.required_layer_thickness_mm is None:
            return material
        return f"{material} at {policy.required_layer_thickness_mm:.3f} mm"

    def _layer_thickness_matches(self, actual_value, required_value: Optional[float]) -> bool:
        if required_value is None:
            return True
        try:
            return abs(float(actual_value) - float(required_value)) < 1e-6
        except (TypeError, ValueError):
            return False

    def _material_label_matches(
        self, actual_label: Optional[str], required_label: Optional[str]
    ) -> bool:
        if not required_label:
            return True
        actual = (actual_label or "").strip().lower()
        required = (required_label or "").strip().lower()
        if not actual or not required:
            return False
        return actual == required or actual.startswith(f"{required} ")

    def _splint_orientation_failure_reason(self) -> str:
        return "Splint auto-orient API response did not meet the required tilted orientation profile."

    def _build_splint_dental_layout_params(
        self, batch_api_params: Dict, policy: ResolvedWorkflowPolicy
    ) -> Dict:
        layout_params = dict(batch_api_params)
        layout_params["mode"] = "DENTAL"
        layout_params["allow_overlapping_supports"] = False
        if policy.tilt_degrees is not None:
            layout_params["tilt"] = int(round(float(policy.tilt_degrees)))
        return layout_params

    def _find_required_scene_settings_for_policy(
        self,
        print_settings_for_manifest: Dict,
        payload: Dict,
        policy: ResolvedWorkflowPolicy,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        presets, success = self.api.load_api_presets()
        if not success or not presets:
            return None, "Could not load material presets to resolve required splint print settings."
        required_material = policy.required_material_label
        required_layer = policy.required_layer_thickness_mm
        printer_name = print_settings_for_manifest.get("printer_name") or ""
        machine_type = payload.get("machine_type")
        printer_types = presets.get("printer_types", [])
        matching_printers = []
        if printer_name:
            matching_printers = [pt for pt in printer_types if pt.get("label") == printer_name]
        elif machine_type:
            matching_printers = [
                pt
                for pt in printer_types
                if machine_type in pt.get("supported_machine_type_ids", [])
            ]
        for printer_type in matching_printers:
            for material in printer_type.get("materials", []):
                if not self._material_label_matches(material.get("label"), required_material):
                    continue
                for material_setting in material.get("material_settings", []):
                    scene_settings = dict(material_setting.get("scene_settings", {}))
                    if self._layer_thickness_matches(
                        scene_settings.get("layer_thickness_mm"), required_layer
                    ):
                        return scene_settings, None
        printer_display = printer_name or machine_type or "the selected printer"
        return None, (
            f"Splint printer/material selection does not expose "
            f"{self._format_required_profile(policy)} for {printer_display}."
        )

    # ------------------------------------------------------------------
    # Scene model helpers
    # ------------------------------------------------------------------

    def _get_scene_models(self, scene_id: str) -> List[Dict]:
        scene_info = self.api.get_scene_info(scene_id, use_cache=False)
        models = scene_info.get("models", []) if scene_info else []
        return copy.deepcopy(models)

    def _map_scene_models_to_file_paths(
        self, scene_id: str, expected_paths: List[str]
    ) -> Dict[str, Dict]:
        scene_models = self._get_scene_models(scene_id)
        remaining_models = list(scene_models)
        mapping: Dict[str, Dict] = {}

        def _pop_first_match(predicate) -> Optional[Dict]:
            for index, model in enumerate(remaining_models):
                if predicate(model):
                    return remaining_models.pop(index)
            return None

        for path in expected_paths:
            normalized_path = os.path.normcase(os.path.abspath(path))
            matched = _pop_first_match(
                lambda model: os.path.normcase(
                    os.path.abspath(model.get("original_file") or "")
                )
                == normalized_path
            )
            if matched:
                mapping[path] = matched

        for path in expected_paths:
            if path in mapping:
                continue
            filename = os.path.normcase(os.path.basename(path))
            matched = _pop_first_match(
                lambda model: os.path.normcase(model.get("name") or "") == filename
            )
            if matched:
                mapping[path] = matched

        for path in expected_paths:
            if path in mapping or not remaining_models:
                continue
            mapping[path] = remaining_models.pop(0)

        return mapping

    def _resolve_tooth_model_ids(self, scene_id: str, build_plan: BuildPlan) -> List[str]:
        path_to_model = self._map_scene_models_to_file_paths(
            scene_id, list(build_plan.file_paths)
        )
        tooth_model_ids: List[str] = []
        for path in build_plan.file_paths:
            if build_plan.file_workflows.get(path) != WORKFLOW_TOOTH_MODEL:
                continue
            model = path_to_model.get(path)
            if model and model.get("id"):
                tooth_model_ids.append(model["id"])
        return tooth_model_ids

    def _get_model_dimensions(self, model: Optional[Dict]) -> Tuple[float, float, float]:
        if not model:
            return 0.0, 0.0, 0.0
        bbox = model.get("bounding_box", {})
        min_corner = bbox.get("min_corner", {})
        max_corner = bbox.get("max_corner", {})
        return (
            max_corner.get("x", 0.0) - min_corner.get("x", 0.0),
            max_corner.get("y", 0.0) - min_corner.get("y", 0.0),
            max_corner.get("z", 0.0) - min_corner.get("z", 0.0),
        )

    # ------------------------------------------------------------------
    # Layout / support workflows
    # ------------------------------------------------------------------

    def _run_auto_layout_pass(
        self, scene_id: str, api_params: Dict, pause_evt, cancel_evt
    ) -> Tuple[bool, Optional[str]]:
        layout_status, layout_result = self.api.auto_layout_scene(
            scene_id, api_params, pause_evt, cancel_evt
        )
        if layout_status != "succeeded":
            logging.error("Auto-layout failed: %s - %s", layout_status, layout_result)
            return False, "Auto-layout failed."
        return True, None

    def _run_andent_validation_repair_loop(
        self,
        scene_id: str,
        batch_api_params: Dict,
        pause_evt,
        cancel_evt,
        max_attempts: int = 3,
    ) -> Tuple[bool, Optional[str]]:
        repair_params = dict(batch_api_params)
        repair_params["allow_overlapping_supports"] = False
        base_spacing = float(repair_params.get("model_spacing_mm") or 0.5)
        for attempt in range(max_attempts):
            is_valid, validation = self.api.validate_scene_for_print(
                scene_id, pause_evt, cancel_evt
            )
            if is_valid and not validation.get("has_critical_issues"):
                return True, None
            if attempt >= max_attempts - 1:
                issues = validation.get("issues") or []
                first_issue = issues[0].get("message") if issues else None
                return False, first_issue or "Scene still failed validation after auto-layout repair."
            repair_params["model_spacing_mm"] = base_spacing + (attempt + 1) * 0.5
            self._events.update_status("Repairing scene layout...")
            layout_ok, layout_reason = self._run_auto_layout_pass(
                scene_id, repair_params, pause_evt, cancel_evt
            )
            if not layout_ok:
                return False, layout_reason
        return False, "Scene still failed validation after auto-layout repair."

    def _repair_scene_after_supports(
        self, scene_id: str, batch_api_params: Dict, pause_evt, cancel_evt
    ) -> Tuple[bool, Optional[str]]:
        self._events.update_status("Relayout after supports...")
        repair_params = dict(batch_api_params)
        repair_params["allow_overlapping_supports"] = False
        layout_ok, layout_reason = self._run_auto_layout_pass(
            scene_id, repair_params, pause_evt, cancel_evt
        )
        if not layout_ok:
            return False, layout_reason
        return self._run_andent_validation_repair_loop(
            scene_id, repair_params, pause_evt, cancel_evt
        )

    def _validate_splint_orientation_result(
        self,
        initial_models: List[Dict],
        final_models: List[Dict],
        policy: ResolvedWorkflowPolicy,
    ) -> Tuple[bool, Optional[str]]:
        if not initial_models or not final_models:
            return False, "Splint orientation could not be verified because scene model info was unavailable."
        if len(initial_models) != len(final_models):
            return (
                False,
                "Splint orientation could not be verified because scene model counts changed unexpectedly.",
            )
        required_tilt = float(policy.tilt_degrees or 15.0)
        for index, (initial_model, final_model) in enumerate(
            zip(initial_models, final_models), start=1
        ):
            if policy.requires_supports and not final_model.get("has_supports"):
                return (
                    False,
                    f"Splint support generation did not complete successfully for Model #{index}.",
                )
            _, _, initial_z = self._get_model_dimensions(initial_model)
            _, _, final_z = self._get_model_dimensions(final_model)
            orientation = final_model.get("orientation", {}) or {}
            tilt_metric = max(
                abs(float(orientation.get("x", 0.0))),
                abs(float(orientation.get("y", 0.0))),
            )
            minimum_tilt = max(required_tilt - 3.0, required_tilt * 0.75)
            minimum_height = max(initial_z * 1.8, initial_z + 10.0)
            if tilt_metric < minimum_tilt:
                return False, (
                    f"{self._splint_orientation_failure_reason()} "
                    f"Model #{index} did not retain the required dental tilt."
                )
            if final_z < minimum_height:
                return (
                    False,
                    f"{self._splint_orientation_failure_reason()} Model #{index} stayed too flat.",
                )
        return True, None

    def _apply_splint_orientation_workflow(
        self,
        scene_id: str,
        batch_api_params: Dict,
        policy: ResolvedWorkflowPolicy,
        pause_evt,
        cancel_evt,
    ) -> Tuple[bool, Optional[str]]:
        initial_models = self._get_scene_models(scene_id)
        if not initial_models:
            return (
                False,
                "Splint orientation could not be verified because the imported model was unavailable.",
            )
        splint_layout_params = self._build_splint_dental_layout_params(batch_api_params, policy)
        self._events.set_stage("Arrange")
        self._events.update_status("Auto-orienting splint...")
        orient_status, orient_result = self.api.auto_orient_scene(
            scene_id,
            pause_evt,
            cancel_evt,
            payload={
                "mode": "DENTAL",
                "tilt": int(round(float(policy.tilt_degrees or 15.0))),
            },
        )
        if orient_status != "succeeded":
            logging.error("Splint auto-orient failed: %s - %s", orient_status, orient_result)
            return False, self._splint_orientation_failure_reason()
        self._events.update_status("Performing dental layout...")
        layout_status, layout_result = self.api.auto_layout_scene(
            scene_id, splint_layout_params, pause_evt, cancel_evt
        )
        if layout_status != "succeeded":
            logging.error("Splint dental layout failed: %s - %s", layout_status, layout_result)
            return False, "Splint dental auto-layout failed."
        if policy.requires_supports:
            self._events.update_status("Generating splint supports...")
            support_status, support_result = self.api.auto_support_scene(
                scene_id, pause_evt, cancel_evt, payload=policy.support_payload_override
            )
            if support_status != "succeeded":
                logging.error(
                    "Splint auto-support failed: %s - %s", support_status, support_result
                )
                return False, "Splint support generation failed."
            repair_ok, repair_reason = self._repair_scene_after_supports(
                scene_id, splint_layout_params, pause_evt, cancel_evt
            )
            if not repair_ok:
                return False, repair_reason
        final_models = self._get_scene_models(scene_id)
        return self._validate_splint_orientation_result(initial_models, final_models, policy)

    def _run_tooth_support_workflow(
        self, scene_id: str, build_plan: BuildPlan, pause_evt, cancel_evt
    ) -> Tuple[bool, Optional[str]]:
        self._events.update_status("Generating tooth supports...")
        support_payload = dict(build_plan.policy.support_payload_override)
        if build_plan.contains_ortho and build_plan.contains_tooth:
            tooth_model_ids = self._resolve_tooth_model_ids(scene_id, build_plan)
            if len(tooth_model_ids) != build_plan.tooth_model_count:
                return (
                    False,
                    "Could not map every tooth artifact to a scene model before support generation.",
                )
            support_payload["models"] = tooth_model_ids
        support_status, support_result = self.api.auto_support_scene(
            scene_id, pause_evt, cancel_evt, payload=support_payload
        )
        if support_status != "succeeded":
            logging.error(
                "Tooth auto-support failed: %s - %s", support_status, support_result
            )
            return False, "Tooth support generation failed."
        final_models = self._get_scene_models(scene_id)
        if build_plan.contains_ortho and build_plan.contains_tooth:
            tooth_model_ids_set = set(support_payload.get("models") or [])
            ortho_supported = any(
                model.get("has_supports") and model.get("id") not in tooth_model_ids_set
                for model in final_models
            )
            if ortho_supported:
                return False, "Support generation added supports to ortho models in a mixed build."
        support_count = sum(1 for model in final_models if model.get("has_supports"))
        if support_count <= 0:
            return False, "Tooth support generation produced zero supported models."
        if build_plan.tooth_model_count and support_count < build_plan.tooth_model_count:
            return (
                False,
                "Tooth support generation completed, but fewer supported models were detected "
                "than tooth artifacts in the build.",
            )
        return True, None

    # ------------------------------------------------------------------
    # Build planning
    # ------------------------------------------------------------------

    def _build_execution_plans(
        self,
        all_file_paths: List[str],
        path_to_folder: Dict[str, str],
        api_payload: Dict,
        print_settings_for_manifest: Dict,
        default_batch_size: int,
        spacing_mm: float,
        pre_computed_batches: Optional[List[List[str]]] = None,
    ) -> List[BuildPlan]:
        workflow_mode = self._get_workflow_mode()
        self.manual_review_items = []
        self.manual_review_report_path = None
        if not is_andent_v2_workflow_mode(workflow_mode):
            return [
                BuildPlan(
                    build_id=f"standard-{index:03d}",
                    workflow=WORKFLOW_STANDARD,
                    case_ids=[],
                    file_paths=list(batch),
                    folder_paths=sorted({path_to_folder[path] for path in batch}),
                    policy=self._build_default_policy(approval_only=False),
                    dimensions_complete=False,
                )
                for index, batch in enumerate(pre_computed_batches or [], start=1)
            ]
        printer_name = print_settings_for_manifest.get("printer_name") or ""
        build_plate = (
            get_build_plate_for_printer(printer_name) if printer_name else DEFAULT_BUILD_PLATE
        )
        build_plans, manual_review_items = plan_andent_builds(
            all_file_paths,
            build_plate=build_plate,
            spacing_mm=spacing_mm,
            max_batch_size=default_batch_size,
            fit_probe=None,
        )
        self.manual_review_items = manual_review_items
        if manual_review_items:
            self.manual_review_report_path = self._write_manual_review_report(manual_review_items)
            for item in manual_review_items:
                self.skipped_files.extend(
                    os.path.basename(path) for path in item.file_paths
                )
        return build_plans

    def _write_manual_review_report(
        self, items: List[ManualReviewItem]
    ) -> Optional[str]:
        if not items:
            return None
        output_folder = self.settings.get("output")
        os.makedirs(output_folder, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(output_folder, f"manual_review_{timestamp}.json")
        try:
            payload = {
                "generated_at": datetime.now().isoformat(),
                "items": [
                    {
                        "case_id": item.case_id,
                        "workflow": item.workflow,
                        "reason": item.reason,
                        "file_paths": item.file_paths,
                    }
                    for item in items
                ],
            }
            with open(report_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            logging.info("Wrote manual review report: %s", report_path)
            return report_path
        except Exception as exc:
            logging.error("Failed to write manual review report: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Artifact saving helpers
    # ------------------------------------------------------------------

    def _save_approval_screenshot(
        self, scene_id: str, job_name_base: str, pause_evt, cancel_evt
    ) -> bool:
        screenshot_filename = f"{job_name_base}_preview.png"
        output_folder = self.settings.get("output")
        os.makedirs(output_folder, exist_ok=True)
        screenshot_path = os.path.join(output_folder, screenshot_filename)
        if len(screenshot_path) > MAX_PATH_LENGTH:
            base_name = os.path.splitext(screenshot_filename)[0][:50]
            screenshot_filename = f"{base_name}_preview.png"
            screenshot_path = os.path.join(output_folder, screenshot_filename)
        self._events.update_status(f"Saving '{screenshot_filename}'...")
        success, error = self.api.save_scene_screenshot(
            scene_id, screenshot_path, pause_evt, cancel_evt
        )
        if not success:
            self._events.show_error(
                "Screenshot Error", f"Could not save scene screenshot:\n{error}"
            )
            return False
        return True

    def _save_required_artifacts(
        self,
        scene_id: str,
        build_plan: BuildPlan,
        job_name_base: str,
        pause_evt,
        cancel_evt,
    ) -> Tuple[bool, Optional[str]]:
        if not build_plan.policy.save_form_artifact and not build_plan.policy.save_screenshot_artifact:
            return True, None
        self._events.set_stage("Prepare")
        if build_plan.policy.save_form_artifact and not self._save_scene(
            scene_id, job_name_base, pause_evt, cancel_evt
        ):
            return False, "Failed to save the required .form artifact for unattended V2 output."
        if build_plan.policy.save_screenshot_artifact and not self._save_approval_screenshot(
            scene_id, job_name_base, pause_evt, cancel_evt
        ):
            return (
                False,
                "Failed to save the required screenshot artifact for unattended V2 output.",
            )
        return True, None

    # ------------------------------------------------------------------
    # Printer dispatch helpers
    # ------------------------------------------------------------------

    def _resolve_dispatch_printer_ids(self, selected_printer_ids: List[str]) -> List[str]:
        if not self._is_andent_v2_mode():
            return list(selected_printer_ids)
        printers = getattr(self.local_controller, "printers", None)
        if not isinstance(printers, dict) or not printers:
            return list(selected_printer_ids)
        selected_virtual_ids = [
            pid
            for pid in selected_printer_ids
            if pid in printers and getattr(printers[pid], "is_virtual", False)
        ]
        selected_real_ids = [
            pid
            for pid in selected_printer_ids
            if pid in printers and not getattr(printers[pid], "is_virtual", False)
        ]
        available_virtual_ids = [
            pid for pid, printer in printers.items() if getattr(printer, "is_virtual", False)
        ]
        if self._auto_dispatch_real_printers_enabled():
            if selected_real_ids:
                return selected_real_ids
            if selected_virtual_ids:
                return selected_virtual_ids
            if available_virtual_ids:
                return available_virtual_ids
            return list(selected_printer_ids)
        if selected_virtual_ids:
            return selected_virtual_ids
        if available_virtual_ids:
            return available_virtual_ids
        return []

    def _send_to_printer(
        self,
        scene_id: str,
        material_code: str,
        selected_printer_ids: List[str],
        job_name_base: str,
        pause_evt,
        cancel_evt,
    ) -> Tuple[bool, str]:
        best_printer = self.local_controller._find_best_printer(
            scene_id, material_code, selected_printer_ids
        )
        if not best_printer:
            self._events.show_error(
                "No Printer Found", f"No suitable printer for job {job_name_base}."
            )
            return False, "N/A"
        if best_printer.is_virtual:
            printer_name = best_printer.name
            self._events.update_status(
                f"Simulating print of '{job_name_base}' on '{printer_name}'..."
            )
            logging.info("Intercepted print job for virtual printer %s.", printer_name)
            time.sleep(2)
            self._events.update_status(f"Successfully simulated job on {printer_name}.")
            return True, printer_name
        if self._is_andent_v2_mode() and not self._auto_dispatch_real_printers_enabled():
            self._events.show_error(
                "Real Printer Auto-Dispatch Disabled",
                "Andent V2 only auto-dispatches to real printers when the explicit real-printer mode is enabled.",
            )
            return False, best_printer.name
        printer_name = best_printer.name
        self._events.update_status(f"Sending '{job_name_base}' to printer '{printer_name}'...")
        success, error = self.api.send_scene_to_local_printer(
            scene_id, printer_name, job_name_base, pause_evt, cancel_evt
        )
        if success:
            self._events.update_status(f"Successfully sent job to {printer_name}.")
            est_time = self.api.estimate_print_time(scene_id)
            best_printer.available_at_s = time.time() + est_time
            best_printer.is_printing = True
            return True, printer_name
        else:
            self._events.show_error(
                "Upload Failed", f"Could not send job to {printer_name}:\n{error}"
            )
            return False, printer_name

    # ------------------------------------------------------------------
    # Scene file operations
    # ------------------------------------------------------------------

    def _cleanup_scene(self, scene_id: str):
        try:
            self.api.delete_scene(scene_id)
        except Exception as e:
            logging.error("Failed to cleanup scene %s: %s", scene_id, e)

    def _save_scene(
        self, scene_id: str, job_name_base: str, pause_evt, cancel_evt
    ) -> bool:
        return (
            self._save_scene_file(
                scene_id,
                f"{job_name_base}.form",
                pause_evt,
                cancel_evt,
                error_title="File Save Error",
            )
            is not None
        )

    def _save_failed_scene(
        self, scene_id: str, job_name_base: str, pause_evt, cancel_evt
    ) -> Optional[str]:
        saved_filename = self._save_scene_file(
            scene_id,
            f"{job_name_base}_FAILED.form",
            pause_evt,
            cancel_evt,
            error_title="Recovery Save Error",
        )
        if saved_filename:
            self._events.update_status(f"Saved recovery layout as '{saved_filename}'.")
        return saved_filename

    def _save_scene_file(
        self,
        scene_id: str,
        form_filename: str,
        pause_evt,
        cancel_evt,
        error_title: str,
    ) -> Optional[str]:
        output_folder = self.settings.get("output")
        os.makedirs(output_folder, exist_ok=True)
        form_filepath = os.path.join(output_folder, form_filename)
        if len(form_filepath) > MAX_PATH_LENGTH:
            logging.warning("Path too long, truncating: %s", form_filepath)
            base_name, ext = os.path.splitext(form_filename)
            safe_filename = f"{base_name[:50]}{ext}"
            form_filepath = os.path.join(output_folder, safe_filename)
            form_filename = safe_filename
        self._events.update_status(f"Saving '{form_filename}'...")
        save_ok, save_err = self.api.save_scene(
            scene_id, form_filepath, pause_evt, cancel_evt
        )
        if not save_ok:
            self._events.show_error(error_title, f"Could not save .form file:\n{save_err}")
            return None
        return form_filename

    # ------------------------------------------------------------------
    # Result data builder
    # ------------------------------------------------------------------

    def _build_session_result_data(
        self,
        file_label: str,
        model_count: int,
        batch_start_time: float,
        printer_name_for_display: str,
        total_original_volume: Optional[float] = None,
        hollowed_vol: Optional[float] = None,
    ) -> Dict[str, str]:
        processing_time = time.time() - batch_start_time
        mins, secs = divmod(processing_time, 60)
        result_data = {
            "file": file_label,
            "models": model_count,
            "time": f"{int(mins):02d}:{int(secs):02d}",
            "printer": printer_name_for_display,
        }
        if total_original_volume is None or hollowed_vol is None:
            result_data.update(
                {
                    "original_volume": "",
                    "hollowed_volume": "",
                    "resin_saved": "",
                    "avg_resin": "",
                }
            )
            return result_data
        resin_saved_total = max(0.0, total_original_volume - hollowed_vol)
        result_data.update(
            {
                "original_volume": f"{total_original_volume:.2f}",
                "hollowed_volume": f"{hollowed_vol:.2f}",
                "resin_saved": f"{resin_saved_total:.2f}",
                "avg_resin": f"{hollowed_vol / model_count if model_count else 0:.2f}",
            }
        )
        return result_data

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def _generate_reports(
        self,
        scene_id: str,
        current_batch_paths: List[str],
        job_name_base: str,
        printer_name: str,
        batch_start_time: float,
        save_only: bool,
        hollowed_vol: float = 0.0,
        total_original_volume: float = 0.0,
    ):
        task = (
            scene_id,
            current_batch_paths,
            job_name_base,
            printer_name,
            batch_start_time,
            save_only,
            hollowed_vol,
            total_original_volume,
        )
        self._report_queue.put(task)
        logging.debug("OPT-10: Queued report generation for %s", job_name_base)

    def _generate_reports_sync(
        self,
        scene_id: str,
        current_batch_paths: List[str],
        job_name_base: str,
        printer_name: str,
        batch_start_time: float,
        save_only: bool,
        hollowed_vol: float = 0.0,
        total_original_volume: float = 0.0,
    ):
        processing_time = time.time() - batch_start_time
        mins, secs = divmod(processing_time, 60)
        time_str = f"{int(mins):02d}:{int(secs):02d}"
        detailed_report_rows = []
        hollow_ratio = hollowed_vol / total_original_volume if total_original_volume > 0 else 0
        for path in current_batch_paths:
            if self._can_use_feature(LICENSE_FEATURE_ADVANCED_STATS):
                original_vol = self.local_controller.get_cached_volume(path)
                detailed_report_rows.append(
                    {
                        "stl_file_name": os.path.basename(path),
                        "print_job_name": job_name_base,
                        "models": 1,
                        "original_volume": f"{original_vol:.2f}",
                        "hollowed_volume": f"{original_vol * hollow_ratio:.2f}",
                        "resin_saved": f"{original_vol * (1 - hollow_ratio):.2f}",
                        "avg_resin": f"{original_vol * hollow_ratio:.2f}",
                        "processing_time": time_str,
                        "printer": printer_name,
                    }
                )
            else:
                detailed_report_rows.append(
                    {
                        "stl_file_name": os.path.basename(path),
                        "print_job_name": job_name_base,
                        "models": 1,
                        "original_volume": "N/A (License Required)",
                        "hollowed_volume": "N/A (License Required)",
                        "resin_saved": "N/A (License Required)",
                        "avg_resin": "N/A (License Required)",
                        "processing_time": time_str,
                        "printer": printer_name,
                    }
                )
        if detailed_report_rows:
            self._events.auto_save_detailed_report(detailed_report_rows, job_name_base)

    # ------------------------------------------------------------------
    # Archive helper
    # ------------------------------------------------------------------

    def _archive_single_file(
        self, path: str, archive_path: str
    ) -> Tuple[str, bool, str]:
        try:
            dest_path = os.path.join(archive_path, os.path.basename(path))
            if os.path.exists(dest_path):
                base, ext = os.path.splitext(os.path.basename(path))
                counter = 1
                while os.path.exists(dest_path):
                    dest_path = os.path.join(archive_path, f"{base}_{counter}{ext}")
                    counter += 1
            shutil.move(path, dest_path)
            return (path, True, "")
        except Exception as e:
            return (path, False, str(e))

    def archive_processed_files(
        self, file_paths: List[str], archive_subfolder_name: str
    ) -> List[str]:
        used_folder_base = self.settings.get("used")
        if not used_folder_base or not isinstance(used_folder_base, str):
            logging.error(
                "'Used STLs' folder path is not configured. Cannot archive processed files."
            )
            return []
        try:
            daily_used_folder = os.path.join(
                used_folder_base, datetime.now().strftime("%Y-%m-%d")
            )
            archive_path = os.path.join(daily_used_folder, archive_subfolder_name)
            os.makedirs(archive_path, exist_ok=True)
        except (OSError, TypeError) as e:
            logging.error("Could not create archive directory: %s", e)
            return []
        max_workers = min(4, len(file_paths))
        processed_paths = []
        if max_workers <= 1 or len(file_paths) <= 2:
            for path in file_paths:
                _, success, error = self._archive_single_file(path, archive_path)
                if success:
                    processed_paths.append(path)
                else:
                    logging.error("Failed to archive %s: %s", os.path.basename(path), error)
        else:
            with ThreadPoolExecutor(
                max_workers=max_workers, thread_name_prefix="Archiver"
            ) as executor:
                futures = {
                    executor.submit(self._archive_single_file, path, archive_path): path
                    for path in file_paths
                }
                for future in as_completed(futures):
                    path, success, error = future.result()
                    if success:
                        processed_paths.append(path)
                    else:
                        logging.error(
                            "Failed to archive %s: %s", os.path.basename(path), error
                        )
        logging.debug("OPT-7: Archived %d/%d files", len(processed_paths), len(file_paths))
        return processed_paths

    # ------------------------------------------------------------------
    # Main processing loop (extracted from ProcessingController)
    # ------------------------------------------------------------------

    def _run_processing_loop(
        self,
        folders_to_process: List[str],
        api_payload: Dict,
        print_settings_for_manifest: Dict,
        selected_printer_ids: List[str],
        pause_evt,
        cancel_evt,
        save_only: bool = False,
        save_form_files: bool = False,
    ):
        self.skipped_files = []
        self.manual_review_items = []
        self.manual_review_report_path = None
        total_processed_files = 0
        session_total_resin_saved = 0.0
        total_import_time_s = 0.0
        import_batches_timed = 0
        total_layout_time_s = 0.0
        layout_batches_timed = 0
        total_validation_time_s = 0.0
        validation_batches_timed = 0

        all_stls_to_process = []
        files_in_folder = {}
        done_in_folder = {}
        started_folders = set()

        for folder_path in folders_to_process:
            try:
                stls = [
                    (os.path.join(folder_path, f), folder_path)
                    for f in os.listdir(folder_path)
                    if f.lower().endswith(".stl")
                ]
                if stls:
                    all_stls_to_process.extend(stls)
                    files_in_folder[folder_path] = len(stls)
                    done_in_folder[folder_path] = 0
            except OSError as e:
                logging.error("Cannot read folder %s: %s", folder_path, e)
                self._events.update_folder_status(folder_path, "Error")

        if not all_stls_to_process:
            def _safe_count_non_stl(folder):
                try:
                    return len(
                        [f for f in os.listdir(folder) if not f.lower().endswith(".stl")]
                    )
                except OSError:
                    return 0

            total_files_found = sum(
                _safe_count_non_stl(folder)
                for folder in folders_to_process
                if os.path.isdir(folder)
            )
            error_msg = (
                f"No STL files found in the selected {len(folders_to_process)} folder(s).\n\n"
                f"Total non-STL files found: {total_files_found}\n\n"
                "Please select folders containing .stl files."
            )
            logging.warning("No STL files found in %d folders", len(folders_to_process))
            self._events.update_status("No STL files found.")
            self._events.show_error("No Files to Process", error_msg)
            self._events.processing_finished(0, 0, [])
            self._last_processed_count = 0
            self._last_resin_saved = 0.0
            return

        material_code = api_payload.get("material_code")
        if not save_only and "fps_file" not in api_payload and not material_code:
            self._events.show_error(
                "Settings Error", "A material must be selected to match printers."
            )
            self._events.processing_finished(0, 0, [])
            self._last_processed_count = 0
            self._last_resin_saved = 0.0
            return

        self._start_report_worker()

        if self.settings.get("save_form_files") and not save_only:
            self._start_form_export_worker()

        batch_size = self.settings.get("api_params").get("max_batch_size", 10)
        enable_smart_batching = self.settings.get("enable_smart_batching")
        spacing_mm = self.settings.get("api_params").get("model_spacing_mm", 0.5)
        workflow_mode = self._get_workflow_mode()

        path_to_folder = {path: folder for path, folder in all_stls_to_process}
        all_file_paths = [path for path, folder in all_stls_to_process]

        pre_computed_batches = []
        if not is_andent_v2_workflow_mode(workflow_mode) and enable_smart_batching:
            self._events.update_status("Calculating optimal batch sizes...")
            logging.info("Smart batching enabled: analyzing %d files", len(all_file_paths))
            build_plate = DEFAULT_BUILD_PLATE
            optimizer = BatchOptimizer(
                build_plate=build_plate,
                spacing_mm=spacing_mm,
                efficiency=PACKING_EFFICIENCY,
                max_batch_size=MAX_BATCH_SIZE_CAP,
            )
            pre_computed_batches = optimizer.calculate_batches(
                all_file_paths, fallback_batch_size=batch_size
            )
            batch_sizes = [len(b) for b in pre_computed_batches]
            logging.info(
                "Smart batching result: %d batches, sizes: %s",
                len(pre_computed_batches),
                batch_sizes,
            )
        elif not is_andent_v2_workflow_mode(workflow_mode):
            logging.info("Fixed batching: batch_size=%d", batch_size)
            for i in range(0, len(all_file_paths), batch_size):
                pre_computed_batches.append(all_file_paths[i : i + batch_size])

        self._events.update_status("Classifying files and planning batches...")
        _planning_t0 = time.perf_counter()
        execution_plans = self._build_execution_plans(
            all_file_paths,
            path_to_folder,
            api_payload,
            print_settings_for_manifest,
            default_batch_size=batch_size,
            spacing_mm=spacing_mm,
            pre_computed_batches=pre_computed_batches,
        )
        logging.info(
            "Planning phase completed in %.2fs (%d execution plan(s))",
            time.perf_counter() - _planning_t0,
            len(execution_plans),
        )

        if not execution_plans and self.manual_review_items:
            warning = f"{len(self.manual_review_items)} case(s) were held for manual review."
            if self.manual_review_report_path:
                warning = f"{warning}\n\nReview report:\n{self.manual_review_report_path}"
            self._events.show_warning("Manual Review Required", warning)
            self._events.processing_finished(0, 0, self.skipped_files, 0)
            self._last_processed_count = 0
            self._last_resin_saved = 0.0
            return

        batch_num = 1
        folder_batch_counters: Dict[str, int] = {}
        total_batches = len(execution_plans)
        seen_filenames: Dict[str, str] = {}

        skip_print_stage = save_only
        self._events.show_stages(
            skip_export=not save_form_files and not save_only and not skip_print_stage,
            skip_print=skip_print_stage,
        )

        try:
            for build_plan in execution_plans:
                if cancel_evt.is_set():
                    break

                batch_start_time = time.time()
                scene_handed_off_to_export = False
                current_batch_paths = list(build_plan.file_paths)
                batch_api_params = self._resolve_api_params_for_policy(build_plan.policy)
                effective_save_only = save_only or build_plan.policy.approval_only
                dispatch_printer_ids = self._resolve_dispatch_printer_ids(selected_printer_ids)
                scene_payload, scene_payload_error = self._resolve_scene_payload_for_policy(
                    api_payload, print_settings_for_manifest, build_plan.policy
                )
                current_batch_items = [
                    (path, path_to_folder[path]) for path in current_batch_paths
                ]

                if scene_payload_error:
                    logging.warning(
                        "Manual review required for batch %d: %s",
                        batch_num,
                        scene_payload_error,
                    )
                    self.manual_review_items.append(
                        ManualReviewItem(
                            case_id=",".join(build_plan.case_ids) or build_plan.build_id,
                            file_paths=current_batch_paths,
                            reason=scene_payload_error,
                            workflow=build_plan.workflow,
                        )
                    )
                    self.manual_review_report_path = self._write_manual_review_report(
                        self.manual_review_items
                    )
                    batch_num += 1
                    continue

                self._events.update_status(
                    f"Validating batch {batch_num}/{total_batches}..."
                )
                batch_validation = validate_stl_batch(
                    current_batch_paths, seen_filenames=seen_filenames
                )

                if batch_validation.invalid_count > 0:
                    for file_path, result in batch_validation.invalid_files.items():
                        filename = os.path.basename(file_path)
                        self.skipped_files.append(filename)
                        logging.warning("Skipping invalid: %s - %s", file_path, result.message)
                    valid_paths = set(batch_validation.valid_files)
                    current_batch_items = [
                        (p, f) for p, f in current_batch_items if p in valid_paths
                    ]
                    current_batch_paths = [
                        p for p in current_batch_paths if p in valid_paths
                    ]
                    for path, folder in [
                        (p, path_to_folder[p])
                        for p in batch_validation.invalid_files.keys()
                    ]:
                        done_in_folder[folder] = done_in_folder.get(folder, 0) + 1

                if not current_batch_items:
                    logging.info("Batch %d empty after validation - skipping", batch_num)
                    batch_num += 1
                    continue

                logging.info(
                    "Batch %d validation: %d/%d valid",
                    batch_num,
                    batch_validation.valid_count,
                    batch_validation.total_files,
                )

                self._events.update_status(f"Analyzing volumes for Batch #{batch_num}...")
                _vol_t0 = time.perf_counter()
                self.local_controller._parallel_calculate_volumes(current_batch_paths)
                logging.info(
                    "Batch #%d: volume_calc=%.2fs", batch_num, time.perf_counter() - _vol_t0
                )

                self._events.update_status(
                    f"Processing Batch #{batch_num}/{total_batches} ({len(current_batch_paths)} models)..."
                )
                self._events.reset_batch_progress(len(current_batch_paths))

                logging.info(
                    "Creating scene for batch #%d with %d models",
                    batch_num,
                    len(current_batch_paths),
                )

                _scene_t0 = time.perf_counter()
                scene_id = self._get_precreated_scene()
                if scene_id is None:
                    scene_id, err = self.api.create_scene(scene_payload)
                    if err:
                        self._events.show_error(
                            "Scene Error",
                            f"Could not create scene for batch #{batch_num}: {err}",
                        )
                        for path, folder in current_batch_items:
                            self.skipped_files.append(os.path.basename(path))
                            done_in_folder[folder] = done_in_folder.get(folder, 0) + 1
                        continue
                    logging.info(
                        "Batch #%d: scene_create=%.2fs (fresh)",
                        batch_num,
                        time.perf_counter() - _scene_t0,
                    )
                else:
                    err = None
                    logging.info(
                        "Batch #%d: scene_create=%.2fs (pre-created)",
                        batch_num,
                        time.perf_counter() - _scene_t0,
                    )

                self.current_scene_id = scene_id

                layer_thickness = scene_payload.get("layer_thickness_mm", "unknown")
                logging.info(
                    "Scene %s created with layer_thickness: %smm", scene_id, layer_thickness
                )
                if "fps_file" in scene_payload:
                    logging.info(
                        "Scene using FPS file: %s",
                        os.path.basename(scene_payload["fps_file"]),
                    )

                successful_scans_in_batch = 0
                batch_file_paths = [path for path, _ in current_batch_items]

                for _, folder in current_batch_items:
                    if folder not in started_folders:
                        self._events.update_folder_status(folder, "Processing...")
                        started_folders.add(folder)

                use_batch_import = (
                    ENABLE_BATCH_IMPORT and len(batch_file_paths) <= BATCH_IMPORT_LIMIT
                )
                import_start_time = time.perf_counter()

                if use_batch_import:
                    self._events.set_stage("Import")
                    self._events.update_status(
                        f"Batch importing {len(batch_file_paths)} files..."
                    )
                    logging.info("Using batch import for %d files", len(batch_file_paths))

                    def batch_progress_callback(progress: float):
                        bounded_progress = max(0.0, min(progress or 0.0, 1.0))
                        progress_value = max(
                            1,
                            min(
                                len(batch_file_paths),
                                int(round(bounded_progress * len(batch_file_paths))),
                            ),
                        )
                        self._events.set_batch_progress_value(progress_value)

                    batch_status, batch_result = self.api.process_files_batch_into_scene(
                        scene_id,
                        batch_file_paths,
                        batch_api_params,
                        pause_evt,
                        cancel_evt,
                        batch_progress_callback,
                    )

                    if batch_status == "succeeded":
                        successful_scans_in_batch = len(batch_result.get("successful", []))
                        logging.info(
                            "Batch import succeeded: %d files", successful_scans_in_batch
                        )
                        self._events.set_batch_progress_value(len(batch_file_paths))
                    elif batch_status == "partial":
                        logging.warning("Batch import partial success, handling failures")
                        successful_files, skipped_files_partial = (
                            self.api.handle_partial_batch_failure(
                                scene_id,
                                batch_result,
                                batch_file_paths,
                                batch_api_params,
                                pause_evt,
                                cancel_evt,
                            )
                        )
                        successful_scans_in_batch = len(successful_files)
                        for file_path, error in skipped_files_partial:
                            self.skipped_files.append(os.path.basename(file_path))
                        self._events.set_batch_progress_value(len(batch_file_paths))
                    elif batch_status == "cancelled":
                        logging.info("Batch import cancelled by user")
                    else:
                        logging.warning(
                            "Batch import failed (%s), falling back to parallel mode",
                            batch_status,
                        )
                        use_batch_import = False

                if not use_batch_import:
                    self._events.set_stage("Import")
                    max_workers = batch_api_params.get("max_batch_size", 10)
                    logging.info("Using parallel import with %d workers", max_workers)

                    with ThreadPoolExecutor(
                        max_workers=max_workers, thread_name_prefix="STL_Importer"
                    ) as executor:
                        future_to_item = {
                            executor.submit(
                                self.api.process_file_into_scene,
                                scene_id,
                                stl_path,
                                batch_api_params,
                                pause_evt,
                                cancel_evt,
                            ): (stl_path, folder)
                            for stl_path, folder in current_batch_items
                        }

                        for i, future in enumerate(as_completed(future_to_item)):
                            if cancel_evt.is_set():
                                for f in future_to_item:
                                    f.cancel()
                                break
                            stl_path, folder = future_to_item[future]
                            self._events.set_batch_progress_value(i + 1)
                            self._events.update_status(
                                f"Importing {os.path.basename(stl_path)}..."
                            )
                            try:
                                status, result = future.result()
                                if status == "succeeded":
                                    successful_scans_in_batch += 1
                                else:
                                    logging.error(
                                        "Failed to process %s: %s", stl_path, result
                                    )
                                    self.skipped_files.append(os.path.basename(stl_path))
                            except Exception as exc:
                                logging.error(
                                    "Error processing %s in parallel: %s", stl_path, exc
                                )
                                self.skipped_files.append(os.path.basename(stl_path))

                import_duration_s = time.perf_counter() - import_start_time
                total_import_time_s += import_duration_s
                import_batches_timed += 1
                logging.info(
                    "Batch #%d import stage completed in %.2fs (%d models attempted)",
                    batch_num,
                    import_duration_s,
                    len(batch_file_paths),
                )

                if cancel_evt.is_set():
                    self._cleanup_scene(scene_id)
                    break

                if successful_scans_in_batch == 0:
                    logging.warning("Batch #%d had no successful model imports.", batch_num)
                    self._cleanup_scene(scene_id)
                    self._events.update_overall_progress(len(current_batch_paths))
                    for _, folder in current_batch_items:
                        done_in_folder[folder] = done_in_folder.get(folder, 0) + 1
                    batch_num += 1
                    continue

                self._events.set_stage("Hollow")
                self._events.set_stage("Arrange")
                self._start_scene_precreation(scene_payload, batch_num, total_batches)

                layout_start_time = time.perf_counter()
                if build_plan.policy.workflow == WORKFLOW_SPLINT:
                    layout_status, layout_result = self._apply_splint_orientation_workflow(
                        scene_id, batch_api_params, build_plan.policy, pause_evt, cancel_evt
                    )
                    if not layout_status:
                        logging.warning(
                            "Splint batch %d held for manual review: %s",
                            batch_num,
                            layout_result,
                        )
                        self._cleanup_scene(scene_id)
                        self.manual_review_items.append(
                            ManualReviewItem(
                                case_id=",".join(build_plan.case_ids) or build_plan.build_id,
                                file_paths=current_batch_paths,
                                reason=layout_result
                                or (
                                    "Splint orientation could not be verified to keep support touchpoints "
                                    "off the tooth-contact surface."
                                ),
                                workflow=build_plan.workflow,
                            )
                        )
                        self.manual_review_report_path = self._write_manual_review_report(
                            self.manual_review_items
                        )
                        self._events.update_overall_progress(len(current_batch_paths))
                        for _, folder in current_batch_items:
                            done_in_folder[folder] = done_in_folder.get(folder, 0) + 1
                        batch_num += 1
                        continue
                else:
                    self._events.update_status("Performing auto-layout...")
                    layout_status, layout_result = self.api.auto_layout_scene(
                        scene_id, batch_api_params, pause_evt, cancel_evt
                    )
                    if layout_status != "succeeded":
                        logging.error(
                            "Auto-layout failed for batch #%d: %s - %s",
                            batch_num,
                            layout_status,
                            layout_result,
                        )
                        self._cleanup_scene(scene_id)
                        self._events.update_overall_progress(len(current_batch_paths))
                        for _, folder in current_batch_items:
                            done_in_folder[folder] = done_in_folder.get(folder, 0) + 1
                            if done_in_folder[folder] == files_in_folder[folder]:
                                self._events.update_folder_status(folder, "Failed")
                        batch_num += 1
                        continue

                    if build_plan.policy.requires_supports:
                        tooth_support_ok, tooth_support_reason = (
                            self._run_tooth_support_workflow(
                                scene_id, build_plan, pause_evt, cancel_evt
                            )
                        )
                        if not tooth_support_ok:
                            logging.warning(
                                "Tooth-support batch %d held for manual review: %s",
                                batch_num,
                                tooth_support_reason,
                            )
                            self._cleanup_scene(scene_id)
                            self.manual_review_items.append(
                                ManualReviewItem(
                                    case_id=",".join(build_plan.case_ids)
                                    or build_plan.build_id,
                                    file_paths=current_batch_paths,
                                    reason=tooth_support_reason
                                    or "Tooth support generation failed.",
                                    workflow=build_plan.workflow,
                                )
                            )
                            self.manual_review_report_path = (
                                self._write_manual_review_report(self.manual_review_items)
                            )
                            self._events.update_overall_progress(len(current_batch_paths))
                            for _, folder in current_batch_items:
                                done_in_folder[folder] = done_in_folder.get(folder, 0) + 1
                            batch_num += 1
                            continue

                        repair_ok, repair_reason = self._repair_scene_after_supports(
                            scene_id, batch_api_params, pause_evt, cancel_evt
                        )
                        if not repair_ok:
                            logging.warning(
                                "Support batch %d held for manual review after relayout repair: %s",
                                batch_num,
                                repair_reason,
                            )
                            self._cleanup_scene(scene_id)
                            self.manual_review_items.append(
                                ManualReviewItem(
                                    case_id=",".join(build_plan.case_ids)
                                    or build_plan.build_id,
                                    file_paths=current_batch_paths,
                                    reason=repair_reason
                                    or "Scene did not validate after post-support relayout.",
                                    workflow=build_plan.workflow,
                                )
                            )
                            self.manual_review_report_path = (
                                self._write_manual_review_report(self.manual_review_items)
                            )
                            self._events.update_overall_progress(len(current_batch_paths))
                            for _, folder in current_batch_items:
                                done_in_folder[folder] = done_in_folder.get(folder, 0) + 1
                            batch_num += 1
                            continue

                layout_duration_s = time.perf_counter() - layout_start_time
                total_layout_time_s += layout_duration_s
                layout_batches_timed += 1
                logging.info(
                    "Batch #%d auto-layout completed in %.2fs", batch_num, layout_duration_s
                )

                if self.settings.is_print_validation_enabled():
                    self._events.update_status("Validating scene...")
                    validation_start_time = time.perf_counter()
                    if self._is_andent_v2_mode():
                        is_valid, validation_reason = self._run_andent_validation_repair_loop(
                            scene_id, batch_api_params, pause_evt, cancel_evt, max_attempts=2
                        )
                        validation = {
                            "has_critical_issues": not is_valid,
                            "issues": (
                                [{"message": validation_reason}] if validation_reason else []
                            ),
                            "warnings": [],
                        }
                    else:
                        is_valid, validation = self.api.validate_scene_for_print(
                            scene_id, pause_evt, cancel_evt
                        )
                    validation_duration_s = time.perf_counter() - validation_start_time
                    total_validation_time_s += validation_duration_s
                    validation_batches_timed += 1
                    logging.info(
                        "Batch #%d print validation completed in %.2fs",
                        batch_num,
                        validation_duration_s,
                    )

                    if validation.get("has_critical_issues"):
                        if self._is_andent_v2_mode():
                            logging.warning(
                                "Andent V2 scene %s held for manual review after validation repair",
                                scene_id,
                            )
                            self.manual_review_items.append(
                                ManualReviewItem(
                                    case_id=",".join(build_plan.case_ids)
                                    or build_plan.build_id,
                                    file_paths=current_batch_paths,
                                    reason=(
                                        validation.get("issues")
                                        or [
                                            {
                                                "message": "Scene failed validation after auto-layout repair."
                                            }
                                        ]
                                    )[0].get("message"),
                                    workflow=build_plan.workflow,
                                )
                            )
                            self.manual_review_report_path = (
                                self._write_manual_review_report(self.manual_review_items)
                            )
                            self._cleanup_scene(scene_id)
                            self._events.update_overall_progress(len(current_batch_paths))
                            for _, folder in current_batch_items:
                                done_in_folder[folder] = done_in_folder.get(folder, 0) + 1
                            batch_num += 1
                            continue

                        user_choice = self._events.show_validation_dialog(validation)
                        if user_choice == "skip":
                            logging.warning(
                                "Scene %s skipped due to validation issues", scene_id
                            )
                            self._cleanup_scene(scene_id)
                            self._events.update_overall_progress(len(current_batch_paths))
                            for _, folder in current_batch_items:
                                done_in_folder[folder] = done_in_folder.get(folder, 0) + 1
                            batch_num += 1
                            continue
                        elif user_choice == "abort":
                            logging.info("User aborted entire batch due to validation issues")
                            self._cleanup_scene(scene_id)
                            break
                        logging.info("User chose to continue despite validation issues")
                else:
                    self._events.update_status(
                        "Validation disabled; continuing without pre-check"
                    )
                    logging.info(
                        "Print validation disabled; skipping validation for batch #%d", batch_num
                    )

                unique_folders = sorted(
                    list({os.path.basename(item[1]) for item in current_batch_items})
                )
                folder_name_part = "-".join(unique_folders)
                timestamp = datetime.now().strftime("%Y%m%d")

                if folder_name_part not in folder_batch_counters:
                    folder_batch_counters[folder_name_part] = 0
                folder_batch_counters[folder_name_part] += 1
                batch_counter = folder_batch_counters[folder_name_part]

                if build_plan.case_ids:
                    job_name_base = sanitize_filename(build_plan.build_job_name(timestamp))
                else:
                    job_name_base = sanitize_filename(
                        f"{timestamp}_{folder_name_part}_{batch_counter:03d}"
                    )

                printer_name_for_display = "N/A"
                recovery_form_filename = None
                artifact_result_emitted = False
                artifact_file_label = f"{job_name_base}.form"

                artifacts_ok, artifact_error = self._save_required_artifacts(
                    scene_id, build_plan, job_name_base, pause_evt, cancel_evt
                )
                if not artifacts_ok:
                    self.manual_review_items.append(
                        ManualReviewItem(
                            case_id=",".join(build_plan.case_ids) or build_plan.build_id,
                            file_paths=current_batch_paths,
                            reason=artifact_error
                            or "Required unattended output artifacts could not be saved.",
                            workflow=build_plan.workflow,
                        )
                    )
                    self.manual_review_report_path = self._write_manual_review_report(
                        self.manual_review_items
                    )
                    self._cleanup_scene(scene_id)
                    self._events.update_overall_progress(len(current_batch_paths))
                    for _, folder in current_batch_items:
                        done_in_folder[folder] = done_in_folder.get(folder, 0) + 1
                    batch_num += 1
                    continue

                if build_plan.policy.save_form_artifact:
                    self._events.add_result_to_list(
                        self._build_session_result_data(
                            artifact_file_label,
                            len(current_batch_paths),
                            batch_start_time,
                            "Artifact Saved",
                        )
                    )
                    artifact_result_emitted = True

                if effective_save_only:
                    if build_plan.policy.save_form_artifact:
                        success = True
                    else:
                        self._events.set_stage("Prepare")
                        success = self._save_scene(
                            scene_id, job_name_base, pause_evt, cancel_evt
                        )
                    printer_name_for_display = "Saved Output"
                else:
                    self._events.set_stage("Print")
                    success, printer_name_for_display = self._send_to_printer(
                        scene_id,
                        material_code,
                        dispatch_printer_ids,
                        job_name_base,
                        pause_evt,
                        cancel_evt,
                    )
                    if not success:
                        recovery_form_filename = self._save_failed_scene(
                            scene_id, job_name_base, pause_evt, cancel_evt
                        )

                if success:
                    if self._can_use_feature(LICENSE_FEATURE_ADVANCED_STATS):
                        hollowed_vol = self.api.get_scene_stats(scene_id)
                        total_original_volume = sum(
                            self.local_controller.get_cached_volume(p)
                            for p in current_batch_paths
                        )
                        session_total_resin_saved += max(
                            0.0, total_original_volume - hollowed_vol
                        )
                    else:
                        hollowed_vol = 0.0
                        total_original_volume = 0.0

                    self._generate_reports(
                        scene_id,
                        current_batch_paths,
                        job_name_base,
                        printer_name_for_display,
                        batch_start_time,
                        effective_save_only,
                        hollowed_vol=hollowed_vol,
                        total_original_volume=total_original_volume,
                    )

                    result_data = self._build_session_result_data(
                        artifact_file_label
                        if (effective_save_only or build_plan.policy.save_form_artifact)
                        else job_name_base,
                        len(current_batch_paths),
                        batch_start_time,
                        printer_name_for_display,
                        total_original_volume=total_original_volume,
                        hollowed_vol=hollowed_vol,
                    )
                    resin_saved_total = max(0.0, total_original_volume - hollowed_vol)
                    if artifact_result_emitted:
                        self._events.update_latest_result(result_data)
                    else:
                        self._events.add_result_to_list(result_data)

                    total_processed_files += successful_scans_in_batch
                    self._events.record_batch_completion(
                        successful_scans_in_batch, resin_saved_total
                    )

                    if (
                        save_form_files
                        and not effective_save_only
                        and not build_plan.policy.save_form_artifact
                    ):
                        self._queue_form_export(
                            scene_id, job_name_base, batch_num, cleanup_after_export=True
                        )
                        scene_handed_off_to_export = True
                        self.current_scene_id = None
                        logging.info("Queued form export for batch #%d", batch_num)

                    if self.settings.get("archive_processed_stls") is not False:
                        self.archive_processed_files(current_batch_paths, job_name_base)

                elif recovery_form_filename:
                    failed_result = self._build_session_result_data(
                        recovery_form_filename,
                        len(current_batch_paths),
                        batch_start_time,
                        f"{printer_name_for_display} (failed)",
                    )
                    if artifact_result_emitted:
                        failed_result["file"] = artifact_file_label
                        self._events.update_latest_result(failed_result)
                    else:
                        self._events.add_result_to_list(failed_result)

                self._events.update_overall_progress(len(current_batch_paths))
                if not scene_handed_off_to_export:
                    self._cleanup_scene(scene_id)
                    self.current_scene_id = None

                for _, folder in current_batch_items:
                    done_in_folder[folder] = done_in_folder.get(folder, 0) + 1
                    if done_in_folder[folder] == files_in_folder[folder]:
                        self._events.update_folder_status(folder, "Completed")

                batch_num += 1

        finally:
            if self.current_scene_id:
                self._cleanup_scene(self.current_scene_id)

            self._cleanup_precreation()

            if hasattr(self, "_form_export_thread") and self._form_export_thread is not None:
                self._events.update_status("Waiting for form exports to complete...")
                _export_wait_t0 = time.perf_counter()
                self._wait_for_form_exports()
                logging.info(
                    "Post-processing: form_export_wait=%.2fs",
                    time.perf_counter() - _export_wait_t0,
                )

            self._events.update_status("Finalizing reports...")
            _report_wait_t0 = time.perf_counter()
            self._report_queue.join()
            self._stop_report_worker()
            logging.info(
                "Post-processing: report_wait=%.2fs", time.perf_counter() - _report_wait_t0
            )

            if import_batches_timed > 0:
                logging.info(
                    "Stage timing summary: import total %.2fs, avg %.2fs across %s batch(es)",
                    total_import_time_s,
                    total_import_time_s / import_batches_timed,
                    import_batches_timed,
                )
            if layout_batches_timed > 0:
                logging.info(
                    "Stage timing summary: auto-layout total %.2fs, avg %.2fs across %s batch(es)",
                    total_layout_time_s,
                    total_layout_time_s / layout_batches_timed,
                    layout_batches_timed,
                )
            if validation_batches_timed > 0:
                logging.info(
                    "Stage timing summary: validation total %.2fs, avg %.2fs across %s batch(es)",
                    total_validation_time_s,
                    total_validation_time_s / validation_batches_timed,
                    validation_batches_timed,
                )
            else:
                logging.info("Stage timing summary: validation skipped for all batches")

            for folder, total in files_in_folder.items():
                done_count = done_in_folder.get(folder, 0)
                if done_count == 0 and folder not in started_folders:
                    self._events.update_folder_status(folder, "Skipped")
                elif done_count < total:
                    status = "Cancelled" if cancel_evt.is_set() else "Partial"
                    self._events.update_folder_status(folder, status)

            self.local_controller.save_cache()
            self.settings.save()

            if not cancel_evt.is_set():
                self._events.complete_stages()
            self._events.hide_stages()

            if self.manual_review_items:
                warning = f"{len(self.manual_review_items)} case(s) require manual review."
                if self.manual_review_report_path:
                    warning = f"{warning}\n\nReview report:\n{self.manual_review_report_path}"
                self._events.show_warning("Manual Review Required", warning)

            batches_completed = batch_num - 1 if batch_num > 1 else 0
            self._events.processing_finished(
                total_processed_files,
                session_total_resin_saved,
                self.skipped_files,
                batches_completed,
            )

            self._last_processed_count = total_processed_files
            self._last_resin_saved = session_total_resin_saved
