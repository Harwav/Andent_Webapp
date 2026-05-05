"""Generate structural webbing between models on the build platform.

Instead of using a pre-made frame, this module creates a thin sheet
connecting neighboring models. Model footprints (including the inner
U-cavity where fixtures live) are punched out, leaving only the web
connections with tabs and breakaway notches.
"""

from __future__ import annotations

import asyncio
import logging
import math
import sys
from pathlib import Path
from typing import Literal

import numpy as np
import trimesh
from pydantic import BaseModel
from scipy.spatial import ConvexHull
from shapely.geometry import MultiPoint, Polygon

from formlabsAFA.config import BreakawayConfig, TabsConfig, WebbingConfig
from formlabsAFA.mesh.punch import Position

logger = logging.getLogger("formlabsAFA.mesh.webbing")


class ModelFootprint(BaseModel):
    """2D footprint of a model at tab height."""
    filename: str
    position: Position
    # Outer boundary of the cross-section (no holes — covers the U-cavity)
    outer_points: list[list[float]]
    centroid_x: float
    centroid_y: float


def _extract_footprint(
    stl_path: Path, position: Position, tab_height_mm: float
) -> ModelFootprint:
    """Cross-section the model at tab height and extract outer boundary.

    Uses mesh.section() to get the true cross-section polygon, then takes
    the outer ring only (no holes). This follows the U-shape contour while
    covering the inner cavity where the fixture sits.
    """
    mesh = trimesh.load_mesh(str(stl_path))

    section = mesh.section(
        plane_origin=[0, 0, tab_height_mm],
        plane_normal=[0, 0, 1],
    )

    if section is not None:
        try:
            path_2d, _ = section.to_planar()
            polys = path_2d.polygons_full
            if polys:
                biggest = max(polys, key=lambda p: p.area)
                # Outer boundary only — no holes, covers the U-cavity
                outer = Polygon(biggest.exterior)
                pts = np.array(outer.exterior.coords[:-1])  # drop closing duplicate
                centroid = np.array(outer.centroid.coords[0])
                return ModelFootprint(
                    filename=stl_path.name,
                    position=position,
                    outer_points=pts.tolist(),
                    centroid_x=float(position.x + centroid[0]),
                    centroid_y=float(position.y + centroid[1]),
                )
        except Exception as e:
            logger.debug("Section-based footprint failed for %s: %s, using convex hull", stl_path.name, e)

    # Fallback: convex hull of sliced vertices
    sliced = mesh.slice_plane(
        plane_origin=np.array([0.0, 0.0, tab_height_mm]),
        plane_normal=np.array([0.0, 0.0, -1.0]),
        cap=False,
    )
    pts = sliced.vertices[:, :2] if sliced and len(sliced.vertices) >= 3 else mesh.vertices[:, :2]
    hull = ConvexHull(pts)
    hull_pts = hull.points[hull.vertices]
    centroid = np.mean(hull_pts, axis=0)

    return ModelFootprint(
        filename=stl_path.name,
        position=position,
        outer_points=hull_pts.tolist(),
        centroid_x=float(position.x + centroid[0]),
        centroid_y=float(position.y + centroid[1]),
    )


def _face_direction(
    cx_a: float, cy_a: float, cx_b: float, cy_b: float
) -> tuple[str, str]:
    """Determine which face of A faces B and vice versa.

    Returns (face_of_A, face_of_B) where face is one of:
    'front' (-Y), 'back' (+Y), 'left' (-X), 'right' (+X).
    """
    dx = cx_b - cx_a
    dy = cy_b - cy_a

    if abs(dx) > abs(dy):
        return ("right", "left") if dx > 0 else ("left", "right")
    else:
        return ("back", "front") if dy > 0 else ("front", "back")


def _is_face_allowed(face: str, config: WebbingConfig) -> bool:
    return {
        "front": config.connect_front,
        "back": config.connect_back,
        "left": config.connect_left,
        "right": config.connect_right,
    }.get(face, False)


def _create_beam(
    x1: float, y1: float, x2: float, y2: float,
    width: float, height: float,
    overlap_mm: float = 5.0,
    anti_cup_min_span: float = 0.0,
    anti_cup_spacing: float = 0.0,
    anti_cup_width: float = 3.0,
    anti_cup_height: float = 0.6,
) -> trimesh.Trimesh:
    """Create a rectangular beam between two XY points at z=0.

    The beam extends *overlap_mm* past each endpoint so it penetrates
    into the model footprint and creates a solid connection.

    If the beam span exceeds *anti_cup_min_span*, small arched notches
    are cut into the bottom at regular intervals to break the vacuum
    seal against the build platform during peel (anti-cupping).
    """
    dx = x2 - x1
    dy = y2 - y1
    length = math.sqrt(dx * dx + dy * dy)
    if length < 0.01:
        return trimesh.Trimesh()

    angle = math.atan2(dy, dx)
    total_length = length + 2 * overlap_mm
    mid_x = (x1 + x2) / 2
    mid_y = (y1 + y2) / 2

    beam = trimesh.creation.box(extents=[total_length, width, height])

    # Anti-cupping: cut notches along the bottom of long beams
    if anti_cup_min_span > 0 and length > anti_cup_min_span and anti_cup_spacing > 0:
        notches = []
        # Place notches along the beam length in local beam space (centered at origin)
        half = total_length / 2
        pos = -half + anti_cup_spacing
        while pos < half - anti_cup_spacing:
            # Notch is a small cylinder at the bottom of the beam
            notch = trimesh.creation.cylinder(
                radius=anti_cup_width / 2,
                height=width + 2,  # wider than beam so it cuts through
                sections=12,
            )
            # Rotate cylinder to lie along Y axis (across beam width)
            rot90 = trimesh.transformations.rotation_matrix(
                math.radians(90), [1, 0, 0]
            )
            notch.apply_transform(rot90)
            # Center at beam bottom face so only top half-circle cuts in,
            # creating an arch from the build plate
            notch.apply_translation([pos, 0, -height / 2])
            notches.append(notch)
            pos += anti_cup_spacing

        if notches:
            cut_tool = trimesh.util.concatenate(notches)
            beam = beam.difference(cut_tool)

    # Rotate and position in world space
    rot = trimesh.transformations.rotation_matrix(angle, [0, 0, 1])
    beam.apply_transform(rot)
    beam.apply_translation([mid_x, mid_y, height / 2])

    return beam


def _closest_hull_points(
    pts_a: np.ndarray, pts_b: np.ndarray,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Find the closest pair of points between two positioned point sets."""
    min_dist = float("inf")
    best_a = (0.0, 0.0)
    best_b = (0.0, 0.0)

    for pa in pts_a:
        for pb in pts_b:
            d = np.linalg.norm(pa - pb)
            if d < min_dist:
                min_dist = d
                best_a = (float(pa[0]), float(pa[1]))
                best_b = (float(pb[0]), float(pb[1]))

    return best_a, best_b


class WebbingJob(BaseModel):
    model_stl_paths: dict[str, str]  # filename -> stl path on disk
    model_positions: dict[str, dict]  # filename -> {"x", "y", "z"}
    model_orientations: dict[str, dict]  # filename -> {"x", "y", "z"} degrees
    out_path: Path
    webbing: WebbingConfig
    tab_height_mm: float
    tab_connection_distance_mm: float
    breakaway_enabled: bool
    breakaway_mm: float
    breakaway_height_mm: float

    def process(self) -> WebbingDoneResult | WebbingExceptionResult:
        try:
            return self._do_process()
        except Exception as e:
            return WebbingExceptionResult(message=str(e))

    def _do_process(self) -> WebbingDoneResult:
        config = self.webbing
        offset = config.punch_offset_mm

        # 1. Extract convex hull footprints in local space, then rotate + translate
        #    to world space. Uses slice_plane + ConvexHull (same as punch.py — robust).
        footprints: list[dict] = []
        for fname, stl_str in self.model_stl_paths.items():
            pos = self.model_positions[fname]
            orient = self.model_orientations.get(fname, {"x": 0, "y": 0, "z": 0})

            # Step 1a: Load STL, slice at tab height, convex hull (local space)
            mesh = trimesh.load_mesh(stl_str)
            sliced = mesh.slice_plane(
                plane_origin=np.array([0.0, 0.0, self.tab_height_mm]),
                plane_normal=np.array([0.0, 0.0, -1.0]),
                cap=False,
            )
            if sliced is None or len(sliced.vertices) < 3:
                pts2d = mesh.vertices[:, :2]
            else:
                pts2d = sliced.vertices[:, :2]

            hull = ConvexHull(pts2d)
            local_pts = hull.points[hull.vertices]  # Nx2, in model-local space

            # Step 1b: Rotate 2D points by Z-orientation (the only axis that
            # matters for XY footprint — models are already z-up from reorientation)
            z_angle_deg = orient.get("z", 0)
            if z_angle_deg != 0:
                theta = math.radians(z_angle_deg)
                cos_t, sin_t = math.cos(theta), math.sin(theta)
                rotated = np.empty_like(local_pts)
                rotated[:, 0] = local_pts[:, 0] * cos_t - local_pts[:, 1] * sin_t
                rotated[:, 1] = local_pts[:, 0] * sin_t + local_pts[:, 1] * cos_t
                local_pts = rotated

            # Step 1c: Translate to world position
            world_pts = local_pts + np.array([pos["x"], pos["y"]])
            centroid = np.mean(world_pts, axis=0)

            footprints.append({
                "filename": fname,
                "world_pts": world_pts,
                "cx": float(centroid[0]),
                "cy": float(centroid[1]),
            })

        if len(footprints) < 2:
            raise ValueError("Need at least 2 models for webbing")

        # 2. Gabriel graph — edge (i,j) exists only if no other centroid
        #    lies inside the circle with (i,j) as diameter. Produces fewer,
        #    better-justified connections than K-NN. Eliminates tangent beams.
        centroids = np.array([[fp["cx"], fp["cy"]] for fp in footprints])
        n = len(centroids)

        edges: set[tuple[int, int]] = set()
        for i in range(n):
            for j in range(i + 1, n):
                mid = (centroids[i] + centroids[j]) / 2
                radius = np.linalg.norm(centroids[i] - centroids[j]) / 2
                is_gabriel = True
                for k in range(n):
                    if k == i or k == j:
                        continue
                    if np.linalg.norm(centroids[k] - mid) < radius:
                        is_gabriel = False
                        break
                if is_gabriel:
                    edges.add((i, j))

        # Build Shapely polygons for collision checking
        polys = [Polygon(fp["world_pts"].tolist()) for fp in footprints]

        # 3. Filter edges and generate beams
        beams: list[trimesh.Trimesh] = []
        for i, j in edges:
            fa, fb = footprints[i], footprints[j]

            face_a, face_b = _face_direction(fa["cx"], fa["cy"], fb["cx"], fb["cy"])
            if not _is_face_allowed(face_a, config):
                continue
            if not _is_face_allowed(face_b, config):
                continue

            pt_a, pt_b = _closest_hull_points(fa["world_pts"], fb["world_pts"])

            gap = math.sqrt((pt_a[0] - pt_b[0]) ** 2 + (pt_a[1] - pt_b[1]) ** 2)
            if gap > config.max_span_mm:
                continue

            # Skip beams that cross through another model's footprint
            from shapely.geometry import LineString
            line = LineString([pt_a, pt_b])
            crosses_other = False
            for idx, poly in enumerate(polys):
                if idx == i or idx == j:
                    continue
                if line.intersects(poly):
                    crosses_other = True
                    break
            if crosses_other:
                continue

            beam = _create_beam(
                pt_a[0], pt_a[1], pt_b[0], pt_b[1],
                config.thickness_mm, self.tab_height_mm,
                anti_cup_min_span=config.anti_cup_min_span_mm,
                anti_cup_spacing=config.anti_cup_spacing_mm,
                anti_cup_width=config.anti_cup_width_mm,
                anti_cup_height=config.anti_cup_height_mm,
            )
            if len(beam.vertices) > 0:
                beams.append(beam)

        # 4. Perimeter rail — trace around the outermost footprint points
        if config.perimeter_rail and len(footprints) >= 3:
            all_outer_pts = np.vstack([fp["world_pts"] for fp in footprints])
            outer_hull = ConvexHull(all_outer_pts)
            perim_pts = all_outer_pts[outer_hull.vertices]

            for k in range(len(perim_pts)):
                p1 = perim_pts[k]
                p2 = perim_pts[(k + 1) % len(perim_pts)]
                seg_len = math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
                if seg_len < 10.0:
                    continue
                beam = _create_beam(
                    float(p1[0]), float(p1[1]), float(p2[0]), float(p2[1]),
                    config.thickness_mm, self.tab_height_mm,
                    overlap_mm=0.0,
                    anti_cup_min_span=config.anti_cup_min_span_mm,
                    anti_cup_spacing=config.anti_cup_spacing_mm,
                    anti_cup_width=config.anti_cup_width_mm,
                    anti_cup_height=config.anti_cup_height_mm,
                )
                if len(beam.vertices) > 0:
                    beams.append(beam)

        if not beams:
            raise ValueError("No valid web connections found between models")

        # 5. Combine all beams into one mesh
        web_mesh = trimesh.util.concatenate(beams)

        # 6. Punch convex hull footprints from web sheet
        #    punch_offset_mm: negative = shrink punch (more web), positive = enlarge
        tools = []
        clearance = 0.1
        for fp in footprints:
            polygon = Polygon(fp["world_pts"].tolist())
            punch_poly = polygon.buffer(offset)
            if punch_poly.is_empty:
                continue

            # Tab pocket — eroded footprint subtracted from web
            eroded = punch_poly.buffer(-self.tab_connection_distance_mm)
            if eroded.is_empty:
                continue
            tool = trimesh.creation.extrude_polygon(
                eroded,
                self.tab_height_mm + 2 * clearance,
                trimesh.transformations.translation_matrix([0, 0, -clearance]),
            )
            tools.append(tool)

            # Breakaway notch
            if self.breakaway_enabled:
                dilated = punch_poly.buffer(self.breakaway_mm).difference(eroded)
                if not dilated.is_empty:
                    notch = trimesh.creation.extrude_polygon(
                        dilated,
                        self.breakaway_height_mm + clearance,
                        trimesh.transformations.translation_matrix(
                            [0, 0, self.tab_height_mm - self.breakaway_height_mm]
                        ),
                    )
                    tools.append(notch)

        if tools:
            web_mesh = web_mesh.difference(tools)

        web_mesh.export(str(self.out_path))
        logger.info(
            "Generated webbing: %d beams, %d models punched",
            len(beams), len(footprints),
        )
        return WebbingDoneResult(beam_count=len(beams))


class WebbingDoneResult(BaseModel):
    status: Literal["DONE"] = "DONE"
    beam_count: int = 0


class WebbingExceptionResult(BaseModel):
    status: Literal["EXCEPTION"] = "EXCEPTION"
    message: str


async def generate_webbing(
    model_positions: dict[str, tuple[dict, dict]],
    model_orientations: dict[str, dict],
    stl_dir: Path,
    webbing_config: WebbingConfig,
    tabs: TabsConfig,
    breakaway_config: BreakawayConfig,
    out_path: Path,
) -> None:
    """Generate webbing mesh and write to out_path."""
    stl_paths = {}
    positions = {}
    for fname, (posn, _bbox) in model_positions.items():
        stl_paths[fname] = str(stl_dir / fname)
        positions[fname] = posn

    job = WebbingJob(
        model_stl_paths=stl_paths,
        model_positions=positions,
        model_orientations=model_orientations,
        out_path=out_path,
        webbing=webbing_config,
        tab_height_mm=tabs.height_mm,
        tab_connection_distance_mm=tabs.frame_connection_distance_mm,
        breakaway_enabled=breakaway_config.enabled,
        breakaway_mm=breakaway_config.width_mm,
        breakaway_height_mm=breakaway_config.height_mm,
    )

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "formlabsAFA.mesh.webbing",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(job.model_dump_json().encode()), timeout=120
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Webbing generation failed: {stderr.decode()}")

    result_data = stdout.decode().strip()
    if '"EXCEPTION"' in result_data:
        result = WebbingExceptionResult.model_validate_json(result_data)
        raise RuntimeError(f"Webbing error: {result.message}")

    logger.info("Webbing generated -> %s", out_path.name)


if __name__ == "__main__":
    data = sys.stdin.buffer.read()
    print(WebbingJob.model_validate_json(data).process().model_dump_json())
