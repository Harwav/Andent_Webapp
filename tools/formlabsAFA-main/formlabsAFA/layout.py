from __future__ import annotations

import asyncio
import enum
import logging
from collections import deque
from dataclasses import dataclass, field

import trimesh

from formlabsAFA.config import FrameConfig, LayoutConfig
from formlabsAFA.frame_profile import FrameProfile
from formlabsAFA.mesh.geometry import Box2D, Point2D, place_models_on_grid
from formlabsAFA.preform.client import PreFormClient
from formlabsAFA.preform.operations import OperationState

logger = logging.getLogger("formlabsAFA.layout")


@enum.unique
class RepositionState(enum.Enum):
    SWAP = 0
    GRID = 1
    FAILED = 2

    def next(self) -> RepositionState:
        return RepositionState(self.value + 1)


@dataclass
class LayoutOutcome:
    success: bool
    model_positions: dict[str, tuple[dict, dict]] = field(default_factory=dict)
    removed_filenames: list[str] = field(default_factory=list)
    error: str = ""


def is_large_model(bounding_box: dict, threshold_mm: float) -> bool:
    return (
        bounding_box["max_corner"]["y"] - bounding_box["min_corner"]["y"]
        > threshold_mm
    )


def large_model_count(bounding_boxes: list[dict], threshold_mm: float) -> int:
    return sum(1 for bb in bounding_boxes if is_large_model(bb, threshold_mm))


async def find_smallest_model_id(
    client: PreFormClient,
    scene_id: str,
    candidate_model_ids: list[str] | None = None,
) -> str | None:
    scene = await client.get_scene(scene_id)
    models = scene["models"]
    if candidate_model_ids:
        models = [m for m in models if m["id"] in candidate_model_ids]
    if not models:
        return None

    def bbox_diag(model: dict) -> float:
        bb = model["bounding_box"]
        dx = bb["max_corner"]["x"] - bb["min_corner"]["x"]
        dy = bb["max_corner"]["y"] - bb["min_corner"]["y"]
        return (dx**2 + dy**2) ** 0.5

    return min(models, key=bbox_diag)["id"]


def check_models_placement(
    models: list[dict],
    frame_mesh: trimesh.Trimesh,
    front_clearance_mm: float,
    back_clearance_mm: float,
) -> tuple[list[dict], list[dict]]:
    badly_placed = []
    well_placed = []

    for model in models:
        bb = model["bounding_box"]
        mn, mx = bb["min_corner"], bb["max_corner"]

        front_box = trimesh.creation.box(
            bounds=[
                [mn["x"], mn["y"], mn["z"]],
                [mx["x"], mn["y"] + front_clearance_mm, mx["z"]],
            ]
        )
        middle_box = trimesh.creation.box(
            bounds=[
                [mn["x"], mn["y"] + front_clearance_mm, mn["z"]],
                [mx["x"], mx["y"] - back_clearance_mm, mx["z"]],
            ]
        )
        back_box = trimesh.creation.box(
            bounds=[
                [mn["x"], mx["y"] - back_clearance_mm, mn["z"]],
                [mx["x"], mx["y"], mx["z"]],
            ]
        )

        front_hit = frame_mesh.intersection(front_box, check_volume=False)
        middle_hit = frame_mesh.intersection(middle_box, check_volume=False)
        back_hit = frame_mesh.intersection(back_box, check_volume=False)

        pos = model.get("position", {})
        pos_str = f"x={pos.get('x', 0):.1f}, y={pos.get('y', 0):.1f}"

        if front_hit.volume > 0:
            badly_placed.append(model)
            logger.debug(
                "BADLY PLACED %s (%s): front clearance hit (vol=%.2f)",
                model["name"], pos_str, front_hit.volume,
            )
        elif back_hit.volume > 0:
            badly_placed.append(model)
            logger.debug(
                "BADLY PLACED %s (%s): back clearance hit (vol=%.2f)",
                model["name"], pos_str, back_hit.volume,
            )
        elif middle_hit.volume == 0:
            badly_placed.append(model)
            logger.debug(
                "BADLY PLACED %s (%s): not supported by frame (middle vol=0)",
                model["name"], pos_str,
            )
        else:
            well_placed.append(model)

    logger.info(
        "Placement check: %d well-placed, %d badly-placed out of %d",
        len(well_placed), len(badly_placed), len(models),
    )
    return badly_placed, well_placed


async def try_layout_with_fallbacks(
    client: PreFormClient,
    scene_id: str,
    model_id_to_filename: dict[str, str],
    frame: FrameProfile,
    layout_config: LayoutConfig,
    frame_config: FrameConfig,
    batch_size: int,
    process_partial: bool,
    min_models: int,
) -> LayoutOutcome:
    bounds_dict = {
        "x_min_mm": frame.layout_bounds.x_min_mm,
        "x_max_mm": frame.layout_bounds.x_max_mm,
        "y_min_mm": frame.layout_bounds.y_min_mm,
        "y_max_mm": frame.layout_bounds.y_max_mm,
    }

    reposition_state = RepositionState.SWAP
    models_to_layout: list[str] | str = "ALL"
    removed: list[str] = []
    model_bboxes: list[dict] = []
    max_iterations = 50
    iteration = 0

    while True:
        iteration += 1
        if iteration > max_iterations:
            logger.error("Layout exceeded %d iterations, giving up", max_iterations)
            return LayoutOutcome(
                success=False,
                removed_filenames=removed,
                error=f"Layout exceeded max iterations ({max_iterations})",
            )

        remaining_count = len(model_id_to_filename)

        if not process_partial and remaining_count < min_models:
            return LayoutOutcome(
                success=False,
                removed_filenames=removed,
                error="Too few models left in batch",
            )

        layout_result = await client.auto_layout(
            scene_id, models_to_layout, layout_config.model_spacing_mm, bounds_dict
        )

        if layout_result.state == OperationState.SUCCEEDED:
            layout_json = layout_result.result
            model_bboxes = [m["bounding_box"] for m in layout_json["models"]]

            model_posns = {
                model_id_to_filename[m["id"]]: (m["position"], m["bounding_box"])
                for m in layout_json["models"]
                if m["id"] in model_id_to_filename
            }

            badly_placed, well_placed = await asyncio.to_thread(
                check_models_placement,
                layout_json["models"],
                frame.mesh,
                frame_config.front_clearance_mm,
                frame_config.back_clearance_mm,
            )

            if len(badly_placed) == 0:
                return LayoutOutcome(
                    success=True,
                    model_positions=model_posns,
                    removed_filenames=removed,
                )

            if len(well_placed) >= (batch_size - 2):
                # Good enough -- remove badly placed and ship
                for model in badly_placed:
                    mid = model["id"]
                    if mid in model_id_to_filename:
                        removed.append(model_id_to_filename.pop(mid))
                    await client.delete_model(scene_id, mid)
                    model_posns.pop(model_id_to_filename.get(mid, ""), None)

                # Rebuild positions without removed models
                model_posns = {
                    model_id_to_filename[m["id"]]: (m["position"], m["bounding_box"])
                    for m in well_placed
                    if m["id"] in model_id_to_filename
                }
                return LayoutOutcome(
                    success=True,
                    model_positions=model_posns,
                    removed_filenames=removed,
                )

            if len(badly_placed) > 1 and reposition_state != RepositionState.FAILED:
                # Try repositioning strategies
                if reposition_state == RepositionState.SWAP:
                    bad_positions = [m["position"] for m in badly_placed]
                    new_positions = deque(bad_positions)
                    new_positions.rotate(1)
                    models_to_reposition = badly_placed
                    # Sequential: scene-editing calls must not be parallel
                    for model, pos in zip(models_to_reposition, new_positions):
                        await client.update_model(
                            scene_id, model["id"], {"position": pos}
                        )

                elif reposition_state == RepositionState.GRID:
                    models = layout_json["models"]
                    positions = [m["position"] for m in models]
                    bounding_boxes = []
                    for i, bb in enumerate(model_bboxes):
                        bounding_boxes.append(
                            Box2D(
                                Point2D(bb["min_corner"]["x"], bb["min_corner"]["y"]),
                                Point2D(bb["max_corner"]["x"], bb["max_corner"]["y"]),
                                Point2D(positions[i]["x"], positions[i]["y"]),
                            )
                        )
                    new_positions = place_models_on_grid(
                        bounding_boxes,
                        positions,
                        frame.spanners,
                        frame.layout_bounds,
                    )
                    # Sequential: scene-editing calls must not be parallel
                    for model, pos in zip(models, new_positions):
                        await client.update_model(
                            scene_id, model["id"], {"position": pos}
                        )

                # Re-check after repositioning
                scene_data = await client.get_scene(scene_id)
                model_posns = {
                    model_id_to_filename[m["id"]]: (m["position"], m["bounding_box"])
                    for m in scene_data["models"]
                    if m["id"] in model_id_to_filename
                }
                badly_placed, well_placed = await asyncio.to_thread(
                    check_models_placement,
                    scene_data["models"],
                    frame.mesh,
                    frame_config.front_clearance_mm,
                    frame_config.back_clearance_mm,
                )

                interferences = await client.get_interferences(scene_id)

                if (
                    len(badly_placed) == 0
                    and len(interferences.get("model_ids", [])) == 0
                ):
                    return LayoutOutcome(
                        success=True,
                        model_positions=model_posns,
                        removed_filenames=removed,
                    )

                reposition_state = reposition_state.next()
                logger.info("Repositioning failed, trying %s", reposition_state.name)
                models_to_layout = "ALL"
                continue

            else:
                # Remove smallest badly-placed model and retry
                if len(well_placed) == 0:
                    continue

                to_remove = await find_smallest_model_id(
                    client,
                    scene_id,
                    [m["id"] for m in badly_placed],
                )
                if to_remove is None:
                    return LayoutOutcome(
                        success=False,
                        removed_filenames=removed,
                        error="No more models to remove",
                    )

                logger.info(
                    "Removing model %s", model_id_to_filename.get(to_remove, to_remove)
                )
                await client.delete_model(scene_id, to_remove)
                if to_remove in model_id_to_filename:
                    removed.append(model_id_to_filename.pop(to_remove))

                if len(badly_placed) == 1:
                    # Removed the last bad model
                    model_posns = {
                        model_id_to_filename[m["id"]]: (
                            m["position"],
                            m["bounding_box"],
                        )
                        for m in well_placed
                        if m["id"] in model_id_to_filename
                    }
                    return LayoutOutcome(
                        success=True,
                        model_positions=model_posns,
                        removed_filenames=removed,
                    )

                reposition_state = RepositionState.SWAP
                continue

        elif layout_result.state == OperationState.FAILED:
            result_data = layout_result.result or {}
            error_code = result_data.get("error", {}).get("code", "")

            if error_code == "OPERATION_FAILED":
                to_remove = await find_smallest_model_id(client, scene_id)
                if to_remove is None:
                    await client.delete_scene(scene_id)
                    return LayoutOutcome(
                        success=False,
                        removed_filenames=removed,
                        error="Layout failed, no models to remove",
                    )
                logger.info(
                    "Layout failed, removing %s",
                    model_id_to_filename.get(to_remove, to_remove),
                )
                await client.delete_model(scene_id, to_remove)
                if to_remove in model_id_to_filename:
                    removed.append(model_id_to_filename.pop(to_remove))
                reposition_state = RepositionState.SWAP
                continue
            else:
                return LayoutOutcome(
                    success=False,
                    removed_filenames=removed,
                    error=f"Unknown layout error: {result_data}",
                )
        else:
            return LayoutOutcome(
                success=False,
                removed_filenames=removed,
                error=f"Unexpected operation state: {layout_result.state}",
            )
