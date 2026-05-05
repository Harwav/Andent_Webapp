from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Annotated, Literal, Union

import numpy as np
import trimesh
from pydantic import BaseModel, Field, TypeAdapter
from scipy.spatial import ConvexHull
from shapely.geometry import Polygon

from formlabsAFA.config import BreakawayConfig, TabsConfig
from formlabsAFA.mesh.geometry import center_mesh_xy

logger = logging.getLogger("formlabsAFA.mesh.punch")


class Position(BaseModel):
    x: float
    y: float
    z: float


class PunchJob(BaseModel):
    frame_path: Path
    model_info: dict[Path, Position]
    out_path: Path
    tab_height_mm: float
    tab_connection_distance_mm: float
    breakaway_enabled: bool
    breakaway_mm: float
    breakaway_height_mm: float

    def process(self) -> PunchDoneResult | PunchExceptionResult:
        try:
            tools = []
            frame = center_mesh_xy(trimesh.load_mesh(self.frame_path))
            for stl, posn in self.model_info.items():
                mesh = trimesh.load_mesh(stl)
                sliced = mesh.slice_plane(
                    plane_origin=np.array([0.0, 0.0, self.tab_height_mm]),
                    plane_normal=np.array([0.0, 0.0, -1.0]),
                    cap=False,
                )
                if sliced is None:
                    raise ValueError(f"Unable to cut mesh {stl} for punching")

                hull = ConvexHull(sliced.vertices[:, :2])
                polygon = Polygon(hull.points[hull.vertices])
                clearance = 0.1

                eroded_polygon = polygon.buffer(-self.tab_connection_distance_mm)
                eroded_tool = trimesh.creation.extrude_polygon(
                    eroded_polygon,
                    self.tab_height_mm + 2 * clearance,
                    trimesh.transformations.translation_matrix(
                        [posn.x, posn.y, -clearance]
                    ),
                )
                tools.append(eroded_tool)

                if self.breakaway_enabled:
                    dilated_polygon = polygon.buffer(self.breakaway_mm).difference(
                        eroded_polygon
                    )
                    dilated_tool = trimesh.creation.extrude_polygon(
                        dilated_polygon,
                        self.breakaway_height_mm + clearance,
                        trimesh.transformations.translation_matrix(
                            [
                                posn.x,
                                posn.y,
                                self.tab_height_mm - self.breakaway_height_mm,
                            ]
                        ),
                    )
                    tools.append(dilated_tool)

            difference = frame.difference(tools)
            difference.export(self.out_path)
            return PunchDoneResult()
        except Exception as e:
            return PunchExceptionResult(message=str(e))


class PunchDoneResult(BaseModel):
    status: Literal["DONE"] = "DONE"


class PunchExceptionResult(BaseModel):
    status: Literal["EXCEPTION"] = "EXCEPTION"
    message: str


PunchResult = TypeAdapter(
    Annotated[
        Union[PunchDoneResult, PunchExceptionResult],
        Field(discriminator="status"),
    ]
)


async def punch_frame(
    frame_path: Path,
    model_positions: dict[Path, Position],
    tabs: TabsConfig,
    breakaway_config: BreakawayConfig,
    out_path: Path,
) -> None:
    job = PunchJob(
        frame_path=frame_path,
        model_info=model_positions,
        out_path=out_path,
        tab_height_mm=tabs.height_mm,
        tab_connection_distance_mm=tabs.frame_connection_distance_mm,
        breakaway_enabled=breakaway_config.enabled,
        breakaway_mm=breakaway_config.width_mm,
        breakaway_height_mm=breakaway_config.height_mm,
    )

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "formlabsAFA.mesh.punch",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(job.model_dump_json().encode()), timeout=60
    )
    if proc.returncode != 0:
        logger.error("Punch subprocess stderr: %s", stderr.decode())
    result = PunchResult.validate_json(stdout)
    if isinstance(result, PunchExceptionResult):
        raise RuntimeError(f"Error punching frame: {result.message}")

    logger.info("Frame punched successfully -> %s", out_path.name)


if __name__ == "__main__":
    data = sys.stdin.buffer.read()
    print(PunchJob.model_validate_json(data).process().model_dump_json())
