from __future__ import annotations

import random

import numpy as np
import trimesh

from formlabsAFA.config import LayoutBounds


class Point2D:
    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

    def __add__(self, other: Point2D) -> Point2D:
        return Point2D(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Point2D) -> Point2D:
        return Point2D(self.x - other.x, self.y - other.y)

    def __repr__(self) -> str:
        return f"Point2D({self.x}, {self.y})"


class Box2D:
    def __init__(
        self,
        min_corner: Point2D,
        max_corner: Point2D,
        origin: Point2D | None = None,
    ):
        self.min_corner = min_corner
        self.max_corner = max_corner
        self.origin = origin if origin is not None else Point2D(0, 0)

    def place_in_corner_of(
        self, boundary_box: Box2D, positive_x: bool, positive_y: bool
    ) -> None:
        start = Point2D(
            self.max_corner.x if positive_x else self.min_corner.x,
            self.max_corner.y if positive_y else self.min_corner.y,
        )
        end = Point2D(
            boundary_box.max_corner.x if positive_x else boundary_box.min_corner.x,
            boundary_box.max_corner.y if positive_y else boundary_box.min_corner.y,
        )
        delta = end - start
        self.min_corner += delta
        self.max_corner += delta
        self.origin += delta

    def place_outside_corner_of(
        self, boundary_box: Box2D, positive_x: bool, positive_y: bool
    ) -> None:
        start = Point2D(
            self.min_corner.x if positive_x else self.max_corner.x,
            self.max_corner.y if positive_y else self.min_corner.y,
        )
        end = Point2D(
            boundary_box.max_corner.x if positive_x else boundary_box.min_corner.x,
            boundary_box.max_corner.y if positive_y else boundary_box.min_corner.y,
        )
        delta = end - start
        self.min_corner -= delta
        self.max_corner -= delta
        self.origin -= delta

    def intersects(self, other: Box2D, tolerance: float = 0.0) -> bool:
        if self.max_corner.x + tolerance < other.min_corner.x:
            return False
        if self.min_corner.x - tolerance > other.max_corner.x:
            return False
        if self.max_corner.y + tolerance < other.min_corner.y:
            return False
        if self.min_corner.y - tolerance > other.max_corner.y:
            return False
        return True


def union_all(boxes: list[Box2D]) -> Box2D:
    if len(boxes) == 0:
        return Box2D(Point2D(0, 0), Point2D(0, 0))
    min_corner = Point2D(
        min(b.min_corner.x for b in boxes),
        min(b.min_corner.y for b in boxes),
    )
    max_corner = Point2D(
        max(b.max_corner.x for b in boxes),
        max(b.max_corner.y for b in boxes),
    )
    return Box2D(min_corner, max_corner)


def center_mesh_xy(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    cx = -0.5 * (mesh.bounds[0][0] + mesh.bounds[1][0])
    cy = -0.5 * (mesh.bounds[0][1] + mesh.bounds[1][1])
    mesh.apply_translation((cx, cy, 0))
    return mesh


def derive_frame_spanners(
    frame_mesh: trimesh.Trimesh, bounds: LayoutBounds
) -> list[Box2D]:
    tool = trimesh.creation.box(
        bounds=[
            [bounds.x_min_mm, bounds.y_min_mm, frame_mesh.bounds[0][2]],
            [bounds.x_max_mm, bounds.y_max_mm, frame_mesh.bounds[1][2]],
        ]
    )
    isect = frame_mesh.intersection([tool])
    bodies = isect.split(only_watertight=False)
    spanners = []
    for body in bodies:
        min_corner = Point2D(body.bounds[0][0], body.bounds[0][1])
        max_corner = Point2D(body.bounds[1][0], body.bounds[1][1])
        spanners.append(Box2D(min_corner, max_corner))
    return spanners


def place_models_on_grid(
    boxes: list[Box2D],
    positions: list[dict],
    spanners: list[Box2D],
    bounds: LayoutBounds,
) -> list[dict]:
    boxes, indices = map(
        list,
        zip(*random.sample(list(zip(boxes, range(len(boxes)))), k=len(boxes))),
    )
    for i, spanner in enumerate(spanners):
        if i >= len(boxes):
            break
        spanner_center_y = (spanner.max_corner.y + spanner.min_corner.y) / 2
        spanner_boxes = boxes[i :: len(spanners)]
        all_boxes_width = sum(
            box.max_corner.x - box.min_corner.x for box in spanner_boxes
        )
        x_offset = (
            bounds.x_max_mm - bounds.x_min_mm - all_boxes_width
        ) / (len(spanner_boxes) + 1)
        x = bounds.x_min_mm + x_offset
        for j in range(i, len(positions), len(spanners)):
            height = boxes[j].max_corner.y - boxes[j].min_corner.y
            y = max(
                bounds.y_min_mm + height / 2,
                min(bounds.y_max_mm - height / 2, spanner_center_y),
            )
            positions[indices[j]]["y"] += (
                y - (boxes[j].max_corner.y + boxes[j].min_corner.y) / 2
            )
            positions[indices[j]]["x"] += x - boxes[j].min_corner.x
            x += (boxes[j].max_corner.x - boxes[j].min_corner.x) + x_offset
    return positions
