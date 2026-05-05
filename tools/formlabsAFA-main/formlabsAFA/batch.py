from __future__ import annotations

import asyncio
import logging
import pathlib
import shutil
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from tempfile import TemporaryDirectory

from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)

from formlabsAFA.config import AppConfig
from formlabsAFA.context import AppContext
from formlabsAFA.db import ModelStatus, ModelStatusEnum, split_model_filename
from formlabsAFA.frame_profile import FrameProfile, select_frame
from formlabsAFA.layout import (
    LayoutOutcome,
    large_model_count,
    try_layout_with_fallbacks,
)
from formlabsAFA.log import console, get_batch_logger, tprint
from formlabsAFA.mesh.chamfer import chamfer_models
from formlabsAFA.mesh.punch import Position, punch_frame
from formlabsAFA.preform.client import PreFormClient
from formlabsAFA.preform.operations import OperationState

logger = logging.getLogger("formlabsAFA.batch")


def _progress_bar() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


@dataclass
class BatchResult:
    batch_number: int
    model_filenames: list[str]
    output_form_file_path: pathlib.Path
    removed_filenames: list[str] = field(default_factory=list)


@dataclass
class FailedBatchResult(BatchResult):
    error_message: str = ""


class BatchOrchestrator:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx

    async def run_batches(self, filenames: list[str]) -> list[BatchResult]:
        batch_size = self.ctx.config.batch.initial_batch_size
        tasks = []

        remaining = list(filenames)
        while remaining:
            batch_files = remaining[:batch_size]
            remaining = remaining[batch_size:]
            batch_number = self.ctx.batch_counter.next()
            tasks.append(
                asyncio.create_task(
                    self._process_and_finalize(batch_files, batch_number)
                )
            )

        if not tasks:
            return []

        tprint(
            f"[cyan]\u25b6[/cyan] Processing [bold]{len(tasks)}[/bold] batch(es) "
            f"from [bold]{len(filenames)}[/bold] models"
        )
        return list(await asyncio.gather(*tasks))

    async def _process_and_finalize(
        self, filenames: list[str], batch_number: int
    ) -> BatchResult:
        ctx = self.ctx
        blog = get_batch_logger(batch_number, ctx.workspace.logs)
        batch_start = datetime.now()

        tprint(
            Panel(
                f"[bold]Batch {batch_number}[/bold] \u2014 {len(filenames)} models",
                expand=False,
            )
        )

        # -- Audit: log batch header, config flags, and every input file --
        config = ctx.config
        blog.info("=" * 60)
        blog.info("BATCH %d START — %d models", batch_number, len(filenames))
        blog.info("=" * 60)
        blog.info("  MODE: %s", config.build.mode)
        blog.info("  MATERIAL: %s / %s / %.2fmm layer",
                  config.material.machine_type, config.material.material_code,
                  config.material.layer_thickness_mm)
        blog.info("  HOLLOW: %s%s%s",
                  "yes" if config.hollowing.enabled else "no",
                  f" (honeycomb)" if config.hollowing.enabled and config.hollowing.honeycomb_infill else "",
                  f" (shell={config.hollowing.shell_thickness_mm}mm)" if config.hollowing.enabled else "")
        blog.info("  DRAIN HOLES: %s",
                  f"yes (r={config.drain_holes.radius_mm}mm, max={config.drain_holes.max_count})" if config.hollowing.enabled else "n/a (not hollowed)")
        blog.info("  CHAMFER: %s", "yes" if config.chamfer.enabled else "no")
        blog.info("  FIXTURE: %s",
                  f"yes ({config.fixture.stl_path})" if config.fixture.enabled else "no")
        blog.info("  LABELS: %s", "yes" if config.model_labels.enabled else "no")
        blog.info("  SUPPORT: %s", "yes" if config.support.support_all_minima else "no")
        if config.build.mode == "frame":
            blog.info("  FRAME: tabs=%.1fmm, breakaway=%s",
                      config.tabs.height_mm,
                      "yes" if config.breakaway.enabled else "no")
        elif config.build.mode == "webbing":
            blog.info("  WEBBING: tabs=%.1fmm, thickness=%.1fmm, breakaway=%s",
                      config.tabs.height_mm, config.webbing.thickness_mm,
                      "yes" if config.breakaway.enabled else "no")
        blog.info("  BATCH SIZE: %d (min=%d, partial=%s)",
                  config.batch.initial_batch_size, config.batch.min_models,
                  "yes" if config.batch.process_partial_batches else "no")
        blog.info("-" * 60)
        for i, f in enumerate(filenames, 1):
            blog.info("  INPUT [%d/%d] %s", i, len(filenames), f)

        await self._set_statuses(filenames, ModelStatusEnum.BATCHED)

        async with ctx.batch_semaphore:
            try:
                result = await self._process_batch(filenames, batch_number, blog)
            except Exception as e:
                logger.exception("Batch %d failed", batch_number)
                result = FailedBatchResult(
                    batch_number=batch_number,
                    model_filenames=filenames,
                    output_form_file_path=pathlib.Path(""),
                    error_message=str(e),
                )

        elapsed = (datetime.now() - batch_start).total_seconds()
        models_to_requeue = list(result.removed_filenames)

        if isinstance(result, FailedBatchResult):
            tprint(
                f"[red bold]\u2718 Batch {batch_number} failed:[/red bold] {result.error_message}"
            )
            blog.error("BATCH %d FAILED: %s", batch_number, result.error_message)
            models_to_requeue.extend(result.model_filenames)
        else:
            await self._move_stls_to_completed(result)
            if ctx.config.printer.upload_to_printer:
                await self._send_batch(result, blog)
            tprint(
                f"[green bold]\u2714 Batch {batch_number} complete[/green bold] "
                f"\u2014 {len(result.model_filenames)} models \u2192 {result.output_form_file_path.name}"
            )
            blog.info("OUTPUT %s", result.output_form_file_path.name)

        # -- Audit: log removed models --
        if result.removed_filenames:
            blog.info("REMOVED %d models during layout:", len(result.removed_filenames))
            for f in result.removed_filenames:
                blog.info("  REMOVED %s", f)

        # -- Audit: batch summary --
        blog.info("-" * 60)
        blog.info(
            "BATCH %d SUMMARY: %s | %d input | %d output | %d removed | %.1fs elapsed",
            batch_number,
            "OK" if not isinstance(result, FailedBatchResult) else "FAILED",
            len(filenames),
            len(result.model_filenames) if not isinstance(result, FailedBatchResult) else 0,
            len(result.removed_filenames),
            elapsed,
        )
        blog.info("-" * 60)

        if models_to_requeue:
            blog.info("REQUEUED %d models for next batch", len(models_to_requeue))
            ctx.model_queue.requeue(models_to_requeue)

        return result

    async def _process_batch(
        self,
        filenames: list[str],
        batch_number: int,
        blog: logging.Logger,
    ) -> BatchResult:
        ctx = self.ctx
        client = ctx.preform_client
        config = ctx.config

        # 1. Merge multi-body STLs (fuses label letters into main arch)
        #    Files are independent — run in parallel threads
        from formlabsAFA.mesh.chamfer import merge_bodies
        tprint("[cyan]\u25b6[/cyan] Merging model bodies...")
        blog.info("STEP merge: fusing multi-body STLs")
        merge_tasks = []
        for f in filenames:
            src = ctx.workspace.stl_input / f
            dst = ctx.chamfer_dir / f
            merge_tasks.append(asyncio.to_thread(merge_bodies, src, dst))
        await asyncio.gather(*merge_tasks)
        tprint(f"[green]\u2714[/green] Merge complete")
        blog.info("STEP merge: complete")

        # 2. Chamfer (operates on merged files in chamfer_dir)
        if config.chamfer.enabled:
            tprint("[cyan]\u25b6[/cyan] Chamfering models...")
            blog.info("STEP chamfer: enabled")
            await chamfer_models(
                filenames, ctx.chamfer_dir, ctx.chamfer_dir, config.chamfer
            )
            tprint(f"[green]\u2714[/green] Chamfer complete")
            blog.info("STEP chamfer: complete")

        # 2. Create scene
        tprint("[cyan]\u25b6[/cyan] Creating scene...")
        scene_id = await client.create_scene(config.material.to_payload())
        files = [ctx.chamfer_dir / f for f in filenames]
        tprint(f"[green]\u2714[/green] Scene created: {scene_id}")
        blog.info("STEP scene: created %s (material=%s)", scene_id, config.material.material_code)

        try:
            # 3. Import models
            model_id_to_filename = await self._import_models(
                client, scene_id, files, config, blog
            )

            # 4. Reorient
            await self._reorient_models(client, scene_id, model_id_to_filename, blog)

            # 5. Auto-support
            if config.support.support_all_minima:
                tprint("[cyan]\u25b6[/cyan] Generating supports...")
                blog.info("STEP support: generating auto-supports")
                await client.auto_support(
                    scene_id, list(model_id_to_filename.keys())
                )
                tprint("[green]\u2714[/green] Supports generated")
                blog.info("STEP support: complete")

            blog.info("STEP import+support: %d models (hollow=%s, support=%s)",
                      len(model_id_to_filename),
                      "yes" if config.hollowing.enabled else "no",
                      "yes" if config.support.support_all_minima else "no")

            # 6. Select frame (frame mode only)
            mode = config.build.mode
            if mode == "frame":
                scene_data = await client.get_scene(scene_id)
                model_bboxes = [m["bounding_box"] for m in scene_data["models"]]
                n_large = large_model_count(
                    model_bboxes, config.frame.large_model_min_y_dim_mm
                )
                frame = select_frame(
                    ctx.frame_profiles,
                    len(filenames),
                    n_large,
                    config.frame.large_frame_cutoff,
                    config.frame.min_large_models_small_frame,
                )
                tprint(f"[green]\u2714[/green] Frame profile: [bold]{frame.name}[/bold]")
                blog.info("STEP frame: selected profile '%s' (%d large models detected)", frame.name, n_large)
            else:
                frame = None
                tprint(f"[green]\u2714[/green] Mode '{mode}' — no frame profile needed")
                blog.info("STEP frame: skipped (mode=%s)", mode)

            # 7. Layout
            tprint("[cyan]\u25b6[/cyan] Running auto-layout...")
            blog.info("STEP layout: starting auto-layout (spacing=%.1fmm, mode=%s)",
                      config.layout.model_spacing_mm, mode)

            if mode == "frame":
                # Frame mode: constrained layout using frame spanners + clearance checks.
                assert frame is not None
                model_orientations = {}  # frame mode: rotation locked
                outcome = await try_layout_with_fallbacks(
                    client,
                    scene_id,
                    model_id_to_filename,
                    frame,
                    config.layout,
                    config.frame,
                    config.batch.initial_batch_size,
                    config.batch.process_partial_batches,
                    config.batch.min_models,
                )
            else:
                # Loose and webbing modes: free auto-layout within configured bounds,
                # rotation unlocked for denser packing.
                bounds_dict = {
                    "x_min_mm": config.free_layout.bounds.x_min_mm,
                    "x_max_mm": config.free_layout.bounds.x_max_mm,
                    "y_min_mm": config.free_layout.bounds.y_min_mm,
                    "y_max_mm": config.free_layout.bounds.y_max_mm,
                }
                layout_result = await client.auto_layout(
                    scene_id, "ALL", config.layout.model_spacing_mm, bounds_dict,
                    lock_rotation=False,
                )
                from formlabsAFA.preform.operations import OperationState
                if layout_result.state == OperationState.SUCCEEDED:
                    layout_json = layout_result.result
                    model_posns = {
                        model_id_to_filename[m["id"]]: (m["position"], m["bounding_box"])
                        for m in layout_json["models"]
                        if m["id"] in model_id_to_filename
                    }
                    model_orientations = {
                        model_id_to_filename[m["id"]]: m.get("orientation", {"x": 0, "y": 0, "z": 0})
                        for m in layout_json["models"]
                        if m["id"] in model_id_to_filename
                    }
                    outcome = LayoutOutcome(success=True, model_positions=model_posns)
                else:
                    outcome = LayoutOutcome(
                        success=False,
                        error=f"Auto-layout failed: {layout_result.state}",
                    )

            if not outcome.success:
                blog.error("STEP layout: FAILED — %s", outcome.error)
                await client.delete_scene(scene_id)
                return FailedBatchResult(
                    batch_number=batch_number,
                    model_filenames=filenames,
                    output_form_file_path=pathlib.Path(""),
                    removed_filenames=outcome.removed_filenames,
                    error_message=outcome.error,
                )

            if outcome.removed_filenames:
                tprint(
                    f"[yellow]\u26a0[/yellow] Removed {len(outcome.removed_filenames)} "
                    f"models that didn't fit"
                )
            blog.info("STEP layout: complete (%d placed, %d removed)", len(outcome.model_positions), len(outcome.removed_filenames))
            tprint(f"[green]\u2714[/green] Layout complete")

            remaining = [f for f in filenames if f not in outcome.removed_filenames]

            # 8. Generate connector (frame/webbing/none)
            batch_uuid = uuid.uuid4()
            batch_path = (
                ctx.workspace.batches_to_print
                / f"b{batch_number:05}_{len(remaining)}x_{batch_uuid}.form"
            )

            with TemporaryDirectory() as tmpdir:
                frame_tmp = pathlib.Path(tmpdir) / "frame.stl"

                if mode == "webbing":
                    from formlabsAFA.mesh.webbing import generate_webbing
                    tprint("[cyan]\u25b6[/cyan] Generating webbing...")
                    await generate_webbing(
                        outcome.model_positions,
                        model_orientations,
                        ctx.workspace.stl_input,
                        config.webbing,
                        config.tabs,
                        config.breakaway,
                        frame_tmp,
                    )
                    await self._add_frame_to_scene(
                        client, scene_id, frame_tmp, batch_number, blog
                    )
                    tprint(f"[green]\u2714[/green] Webbing generated and added")
                    blog.info("STEP webbing: generated for %d models", len(remaining))
                elif mode == "frame":
                    assert frame is not None
                    tprint("[cyan]\u25b6[/cyan] Punching frame...")
                    model_positions = {
                        ctx.workspace.stl_input / fname: Position(
                            x=posn["x"], y=posn["y"], z=posn["z"]
                        )
                        for fname, (posn, _) in outcome.model_positions.items()
                    }
                    await punch_frame(
                        frame.stl_path,
                        model_positions,
                        config.tabs,
                        config.breakaway,
                        frame_tmp,
                    )
                    await self._add_frame_to_scene(
                        client, scene_id, frame_tmp, batch_number, blog
                    )
                    tprint(f"[green]\u2714[/green] Frame punched and added")
                    blog.info("STEP punch: frame punched with %d models", len(remaining))
                else:
                    # Loose mode: no connector, just models (+ optional fixtures + labels).
                    tprint(f"[green]\u2714[/green] Loose mode — no connector")
                    blog.info("STEP connector: skipped (mode=loose)")

            # 8b. Per-model patient-ID labels (any mode)
            #     Runs BEFORE fixtures so a label failure fails fast before we
            #     waste work placing fixtures for a doomed batch.
            if config.model_labels.enabled:
                await self._add_model_labels(
                    client, scene_id, model_id_to_filename,
                    outcome.model_positions, blog,
                )

            # 8c. Fixtures at each model position (any mode)
            if config.fixture.enabled and config.fixture.stl_path:
                fixture_path = pathlib.Path(config.fixture.stl_path)
                if not fixture_path.is_absolute():
                    fixture_path = config.general.base_path / fixture_path
                tprint(f"[cyan]\u25b6[/cyan] Adding fixtures ({len(remaining)} models)...")
                blog.info("STEP fixture: adding %d fixtures from %s", len(remaining), fixture_path.name)
                for fname, (posn, _bbox) in outcome.model_positions.items():
                    # Match the model's orientation (important when rotation is unlocked)
                    orient = model_orientations.get(fname, {"x": 0, "y": 0, "z": 0})
                    fix_result = await client.import_model(
                        scene_id,
                        str(fixture_path),
                        name=f"fixture-{pathlib.Path(fname).stem}",
                        orientation=orient,
                    )
                    await client.update_model(
                        scene_id,
                        fix_result.result["id"],
                        {"position": {"x": posn["x"], "y": posn["y"], "z": posn["z"]}},
                    )
                tprint(f"[green]\u2714[/green] Fixtures added")
                blog.info("STEP fixture: complete")

            # 9. Save
            tprint(f"[cyan]\u25b6[/cyan] Saving {batch_path.name}...")
            await client.save_form(scene_id, str(batch_path))
            tprint(f"[green]\u2714[/green] Saved: {batch_path.name}")
            blog.info("STEP save: %s", batch_path.name)

            await client.delete_scene(scene_id)

            return BatchResult(
                batch_number=batch_number,
                model_filenames=remaining,
                output_form_file_path=batch_path,
                removed_filenames=outcome.removed_filenames,
            )

        except Exception:
            try:
                await client.delete_scene(scene_id)
            except Exception as cleanup_err:
                logger.warning("Failed to clean up scene %s: %s", scene_id, cleanup_err)
            raise

    async def _import_models(
        self,
        client: PreFormClient,
        scene_id: str,
        files: list[pathlib.Path],
        config: AppConfig,
        blog: logging.Logger,
    ) -> dict[str, str]:
        model_id_to_filename: dict[str, str] = {}

        if config.hollowing.enabled:
            tprint(
                f"[cyan]\u25b6[/cyan] Scan-to-model ({len(files)} files, with hollowing)..."
            )
            blog.info("STEP scan-to-model: %d files, hollow=yes, shell=%.1fmm, "
                      "honeycomb=%s, drain_holes(r=%.1fmm, max=%d, "
                      "suppression=%.1fmm, height_ratio=%.2f)",
                      len(files), config.hollowing.shell_thickness_mm,
                      "yes" if config.hollowing.honeycomb_infill else "no",
                      config.drain_holes.radius_mm, config.drain_holes.max_count,
                      config.drain_holes.suppression_distance_mm,
                      config.drain_holes.height_ratio)

            # -- Pass 1: batch scan-to-model with primary drain-hole params --
            payload = self._build_scan_to_model_payload(files, config)
            blog.info("  PASS 1: batch scan-to-model (%d files, primary params)", len(files))
            result = await client.scan_to_model(scene_id, payload)
            for model in result.result["models"]:
                model_id_to_filename[model["id"]] = pathlib.Path(
                    model["original_file"]
                ).name

            if len(model_id_to_filename) < len(files):
                missing = set(f.name for f in files) - set(model_id_to_filename.values())
                blog.error("scan-to-model: only %d/%d models imported. Missing: %s",
                          len(model_id_to_filename), len(files), ", ".join(sorted(missing)))
                raise RuntimeError(
                    f"Only {len(model_id_to_filename)}/{len(files)} models imported "
                    f"(missing: {', '.join(sorted(missing))})"
                )

            blog.info("  PASS 1: %d models imported", len(model_id_to_filename))
            for mid, fname in model_id_to_filename.items():
                blog.info("    IMPORTED %s → %s", fname, mid)

            # -- Validate + identify cup models --
            models_with_cups = await self._validate_and_log(
                client, scene_id, model_id_to_filename, blog, "PASS 1"
            )

            # -- Pass 2: retry cup models individually with relaxed drain-hole params --
            retried_ok: list[str] = []
            still_cupped: list[str] = []

            if models_with_cups:
                dr = config.drain_holes
                blog.info("  PASS 2: retrying %d cup model(s) individually with "
                         "relaxed params (suppression=%.1fmm, height_ratio=%.2f, "
                         "radius=%.1fmm)",
                         len(models_with_cups),
                         dr.retry_suppression_distance_mm,
                         dr.retry_height_ratio, dr.retry_radius_mm)
                tprint(
                    f"[yellow]\u26a0[/yellow] {len(models_with_cups)} model(s) have cups "
                    f"— retrying with relaxed drain-hole params..."
                )

                for old_id in list(models_with_cups):
                    filename = model_id_to_filename[old_id]
                    file_path = self.ctx.chamfer_dir / filename
                    blog.info("    RETRY %s (was %s)", filename, old_id)

                    # Delete the cupped model from scene
                    await client.delete_model(scene_id, old_id)
                    del model_id_to_filename[old_id]

                    # Re-import with relaxed drain-hole params
                    retry_payload = self._build_scan_to_model_payload(
                        [file_path], config, relaxed=True
                    )
                    try:
                        retry_result = await client.scan_to_model(
                            scene_id, retry_payload
                        )
                        new_model = retry_result.result["models"][0]
                        new_id = new_model["id"]
                        model_id_to_filename[new_id] = filename
                        blog.info("    RETRY %s → new id %s", filename, new_id)

                        # Validate the retried model
                        retry_validation = await client.get_print_validation(scene_id)
                        retry_per_model = retry_validation.result.get(
                            "per_model_results", {}
                        )
                        retry_data = retry_per_model.get(new_id, {})
                        retry_cups = retry_data.get("cups", 0)

                        if retry_cups > 0:
                            blog.warning("    RETRY %s: still has cups=%d after "
                                        "relaxed params", filename, retry_cups)
                            still_cupped.append(new_id)
                        else:
                            blog.info("    RETRY %s: cups=0, relaxed params worked",
                                     filename)
                            retried_ok.append(filename)

                    except Exception as e:
                        blog.error("    RETRY %s: scan-to-model failed: %s",
                                  filename, e)
                        still_cupped.append("")  # placeholder for count
                        # Fall through to pass 3 for this model
                        # Re-import raw so it's at least in the scene
                        import_result = await client.import_model(
                            scene_id,
                            str(self.ctx.workspace.stl_input / filename),
                        )
                        new_id = import_result.result["id"]
                        model_id_to_filename[new_id] = filename
                        blog.info("    RETRY %s: fell back to raw import → %s",
                                 filename, new_id)

            # -- Pass 3: models that still have cups after retry → raw import --
            raw_imported: list[str] = []
            if still_cupped:
                real_cupped = [
                    mid for mid in still_cupped
                    if mid and mid in model_id_to_filename
                ]
                if real_cupped:
                    blog.warning("  PASS 3: %d model(s) still cupped after retry, "
                                "reimporting raw (no hollowing)", len(real_cupped))
                    tprint(
                        f"[yellow]\u26a0[/yellow] {len(real_cupped)} model(s) still "
                        f"cupped after retry — importing raw (no hollowing)"
                    )
                    for old_id in real_cupped:
                        filename = model_id_to_filename[old_id]
                        blog.info("    RAW IMPORT %s (was %s)", filename, old_id)
                        await client.delete_model(scene_id, old_id)
                        import_result = await client.import_model(
                            scene_id,
                            str(self.ctx.workspace.stl_input / filename),
                        )
                        new_id = import_result.result["id"]
                        del model_id_to_filename[old_id]
                        model_id_to_filename[new_id] = filename
                        raw_imported.append(filename)
                        blog.warning("    RAW IMPORT %s → %s (NOT HOLLOWED — "
                                    "no drain holes)", filename, new_id)

            # -- Summary --
            hollowed_count = len(model_id_to_filename) - len(raw_imported)
            parts = [f"{hollowed_count} hollowed"]
            if retried_ok:
                parts.append(f"{len(retried_ok)} recovered via retry")
            if raw_imported:
                parts.append(f"{len(raw_imported)} raw (cups persisted)")
            summary = ", ".join(parts)

            tprint(
                f"[green]\u2714[/green] Imported {len(model_id_to_filename)} "
                f"models ({summary})"
            )
            blog.info("STEP scan-to-model: complete — %s", summary)

            if raw_imported:
                blog.warning("ISO NOTICE: %d model(s) shipped without hollowing "
                            "or drain holes: %s",
                            len(raw_imported), ", ".join(raw_imported))

            await self._set_statuses(
                list(model_id_to_filename.values()), ModelStatusEnum.HOLLOWED
            )
        else:
            tprint(f"[cyan]\u25b6[/cyan] Importing {len(files)} models (no hollowing)...")
            blog.info("STEP import: %d files, hollow=no", len(files))
            with _progress_bar() as progress:
                task = progress.add_task("Importing...", total=len(files))
                for file in files:
                    result = await client.import_model(scene_id, str(file))
                    model_id_to_filename[result.result["id"]] = file.name
                    blog.info("  IMPORTED %s → %s", file.name, result.result["id"])
                    progress.update(task, advance=1)
            tprint(f"[green]\u2714[/green] Imported {len(model_id_to_filename)} models")
            blog.info("STEP import: complete — %d models", len(model_id_to_filename))

        return model_id_to_filename

    @staticmethod
    def _build_scan_to_model_payload(
        files: list[pathlib.Path],
        config: AppConfig,
        relaxed: bool = False,
    ) -> dict:
        dr = config.drain_holes
        return {
            "files": [str(f) for f in files],
            "units": "MILLIMETERS",
            "cutoff_height_mm": config.hollowing.cutoff_height_mm,
            "extrude_distance_mm": config.hollowing.extrude_distance_mm,
            "hollow": True,
            "shell_thickness_mm": config.hollowing.shell_thickness_mm,
            "wall_thickness_mm": config.hollowing.hex_wall_thickness_mm,
            "drain_hole_radius_mm": dr.retry_radius_mm if relaxed else dr.radius_mm,
            "drain_hole_height_ratio": dr.retry_height_ratio if relaxed else dr.height_ratio,
            "enable_smooth_contour_extended_sides": False,
            "enable_honeycomb_infill": config.hollowing.honeycomb_infill,
            "drain_hole_suppression_distance_mm": (
                dr.retry_suppression_distance_mm if relaxed
                else dr.suppression_distance_mm
            ),
            "drain_hole_max_count": dr.max_count,
        }

    @staticmethod
    async def _validate_and_log(
        client: PreFormClient,
        scene_id: str,
        model_id_to_filename: dict[str, str],
        blog: logging.Logger,
        pass_label: str,
    ) -> list[str]:
        """Run print-validation, log per-model results, return list of model IDs with cups."""
        validation = await client.get_print_validation(scene_id)
        per_model = validation.result.get("per_model_results", {})

        models_with_cups: list[str] = []
        for mid, data in per_model.items():
            fname = model_id_to_filename.get(mid, mid)
            cups = data.get("cups", 0)
            detail_parts = []
            if cups > 0:
                detail_parts.append(f"cups={cups}")
                models_with_cups.append(mid)

            known_keys = {"cups"}
            extra = {k: v for k, v in data.items() if k not in known_keys}
            if extra:
                detail_parts.append(f"{extra}")

            blog.info("    %s VALIDATION %s: %s", pass_label, fname,
                      ", ".join(detail_parts) if detail_parts else "ok")

        if models_with_cups:
            fnames = [model_id_to_filename.get(m, m) for m in models_with_cups]
            blog.warning("  %s: %d model(s) with cups: %s",
                        pass_label, len(models_with_cups), ", ".join(fnames))
        else:
            blog.info("  %s: all models cup-free", pass_label)

        return models_with_cups

    async def _reorient_models(
        self,
        client: PreFormClient,
        scene_id: str,
        model_id_to_filename: dict[str, str],
        blog: logging.Logger,
    ) -> list[dict]:
        # NOTE: Scene-editing requests must be sequential per PreForm API docs.
        # Parallel update_model calls on the same scene cause race conditions.
        tprint(
            f"[cyan]\u25b6[/cyan] Reorienting {len(model_id_to_filename)} models..."
        )
        bboxes = []
        with _progress_bar() as progress:
            task = progress.add_task("Reorienting...", total=len(model_id_to_filename))
            for model_id, filename in model_id_to_filename.items():
                payload = {
                    "name": pathlib.Path(filename).stem,
                    "orientation": {"z_direction": [0, 0, 1], "x_direction": [1, 0, 0]},
                    "position": {"x": 0, "y": -200, "z": 0},
                }
                result = await client.update_model(scene_id, model_id, payload)
                bboxes.append(result["bounding_box"])
                progress.update(task, advance=1)
        tprint(f"[green]\u2714[/green] Reoriented {len(bboxes)} models")
        blog.info("Reoriented %d models", len(bboxes))
        return bboxes

    async def _add_frame_to_scene(
        self,
        client: PreFormClient,
        scene_id: str,
        frame_path: pathlib.Path,
        batch_number: int,
        blog: logging.Logger,
    ) -> None:
        result = await client.import_model(
            scene_id,
            str(frame_path),
            name="frame-punched",
            orientation={"x": 0, "y": 0, "z": 0},
        )
        frame_model = result.result

        now_str = datetime.now().strftime("%Y%m%d%H%M")
        label = f"Batch_{batch_number}_{now_str}"

        bb = frame_model["bounding_box"]
        try:
            await client.add_label(
                scene_id,
                frame_model["id"],
                label,
                position={
                    "x": bb["max_corner"]["x"] - 2.5,
                    "y": bb["max_corner"]["y"] - 35,
                    "z": bb["max_corner"]["z"] - 1,
                },
                orientation={"x": 0, "y": 0, "z": 90},
            )
            blog.info("Added frame with label: %s", label)
        except Exception:
            blog.warning("Could not add label to frame (non-fatal)")
            logger.warning("Label failed for batch %d — continuing without label", batch_number)

    async def _add_model_labels(
        self,
        client: PreFormClient,
        scene_id: str,
        model_id_to_filename: dict[str, str],
        model_positions: dict[str, tuple[dict, dict]],
        blog: logging.Logger,
    ) -> None:
        """Per-model patient-ID labels. Fails the batch on any failure —
        per-patient traceability is load-bearing for downstream QA."""
        cfg = self.ctx.config.model_labels
        filename_to_model_id = {v: k for k, v in model_id_to_filename.items()}

        tprint(f"[cyan]\u25b6[/cyan] Labeling {len(model_positions)} models...")
        blog.info("STEP model_labels: labeling %d models (bbox_fraction=%s)",
                  len(model_positions), cfg.bbox_fraction)

        for fname, (_posn, bb) in model_positions.items():
            model_id = filename_to_model_id.get(fname)
            if model_id is None:
                raise RuntimeError(
                    f"model_labels: no model_id for filename {fname!r}"
                )
            try:
                _, display_name = split_model_filename(fname)
            except ValueError:
                display_name = pathlib.Path(fname).stem
            label_text = display_name

            mn, mx = bb["min_corner"], bb["max_corner"]
            size_x = mx["x"] - mn["x"]
            size_y = mx["y"] - mn["y"]
            size_z = mx["z"] - mn["z"]
            fx, fy, fz = cfg.bbox_fraction
            ox, oy, oz = cfg.offset_mm
            position = {
                "x": mn["x"] + size_x * fx + ox,
                "y": mn["y"] + size_y * fy + oy,
                "z": mn["z"] + size_z * fz + oz,
            }
            orientation = {
                "x": cfg.orientation_deg[0],
                "y": cfg.orientation_deg[1],
                "z": cfg.orientation_deg[2],
            }

            try:
                await client.add_label(
                    scene_id, model_id, label_text,
                    position=position, orientation=orientation,
                    font_size_mm=cfg.font_size_mm, depth_mm=cfg.depth_mm,
                )
            except Exception as e:
                raise RuntimeError(
                    f"model_labels: failed to label {fname!r} with {label_text!r}: {e}"
                ) from e

        tprint(f"[green]\u2714[/green] Model labels applied")
        blog.info("STEP model_labels: complete")

    async def _send_batch(
        self, batch_result: BatchResult, blog: logging.Logger
    ) -> None:
        ctx = self.ctx
        config = ctx.config.printer
        client = ctx.preform_client

        if config.dashboard_username and config.dashboard_password:
            await client.dashboard_login(
                config.dashboard_username, config.dashboard_password
            )

        tprint(
            f"[cyan]\u25b6[/cyan] Uploading to {config.serial_or_group_queue_id}..."
        )
        load_result = await client.load_form(
            str(batch_result.output_form_file_path)
        )
        scene_id = load_result.result["id"]
        batch_filename = batch_result.output_form_file_path.name

        printers = deque(config.backup_printer_list)
        printer = config.serial_or_group_queue_id

        try:
            print_result = await client.print_scene(
                scene_id, printer, batch_filename
            )
            if print_result.state == OperationState.SUCCEEDED:
                tprint(f"[green]\u2714[/green] Sent to printer: {batch_filename}")
                blog.info("Batch %s sent to printer", batch_filename)
                await self._set_statuses(
                    batch_result.model_filenames,
                    ModelStatusEnum.ENQUEUED,
                    job_name=batch_filename,
                )
                await asyncio.to_thread(
                    shutil.move,
                    str(ctx.workspace.batches_to_print / batch_filename),
                    str(ctx.workspace.batches_printed / batch_filename),
                )
            elif print_result.state == OperationState.FAILED and printers:
                tprint(
                    "[yellow]\u26a0[/yellow] Dashboard print failed, trying backup printer"
                )
                blog.warning("Dashboard print failed, trying backup printer")
                fallback_printer = printers[0]
                printers.rotate()
                await client.print_scene(scene_id, fallback_printer, batch_filename)
            else:
                tprint(
                    f"[red]\u2718[/red] Failed to print batch {batch_filename}"
                )
                blog.error("Failed to print batch %s", batch_filename)
        finally:
            try:
                await client.delete_scene(scene_id)
            except Exception:
                pass

    async def _move_stls_to_completed(self, batch_result: BatchResult) -> None:
        ws = self.ctx.workspace
        tasks = []
        for filename in batch_result.model_filenames:
            src = ws.stl_input / filename
            dst = ws.stl_completed / filename
            tasks.append(asyncio.to_thread(shutil.move, str(src), str(dst)))
        if tasks:
            await asyncio.gather(*tasks)

    async def _set_statuses(
        self,
        filenames: list[str],
        status_value: ModelStatusEnum,
        job_name: str | None = None,
    ) -> None:
        status = ModelStatus(value=status_value, job_name=job_name)
        for filename in filenames:
            try:
                model_id, _ = split_model_filename(filename)
                await self.ctx.db.set_model_status(model_id, status)
            except ValueError:
                pass
