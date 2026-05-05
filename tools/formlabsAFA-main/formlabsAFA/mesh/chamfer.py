from __future__ import annotations

import asyncio
import logging
import shutil
import sys
from pathlib import Path
from typing import Annotated, Literal, Union

import numpy as np
import trimesh
from pydantic import BaseModel, Field

from formlabsAFA.config import ChamferConfig

logger = logging.getLogger("formlabsAFA.mesh.chamfer")


class ChamferJob(BaseModel):
    input_path: Path
    output_path: Path
    height: float
    leg_depth: float

    def process(self) -> ChamferDoneResult | ChamferExceptionResult:
        try:
            mesh = trimesh.load_mesh(str(self.input_path))
            base_z = float(mesh.bounds[0][2])
            y_max = float(mesh.bounds[1][1])

            normal = np.array([0.0, -self.height, self.leg_depth])
            normal /= np.linalg.norm(normal)
            origin = np.array([0.0, y_max, base_z + self.height])

            chamfered = mesh.slice_plane(
                plane_origin=origin, plane_normal=normal, cap=True
            )
            if chamfered is None:
                raise ValueError("Unable to chamfer mesh")

            if not chamfered.is_watertight:
                logger.warning("Chamfered mesh not watertight, attempting repair")
                trimesh.repair.fill_holes(chamfered)

            chamfered.export(self.output_path)
            return ChamferDoneResult()
        except Exception as e:
            return ChamferExceptionResult(message=str(e))


class ChamferDoneResult(BaseModel):
    status: Literal["DONE"] = "DONE"


class ChamferExceptionResult(BaseModel):
    status: Literal["EXCEPTION"] = "EXCEPTION"
    message: str


ChamferResult = Annotated[
    Union[ChamferDoneResult, ChamferExceptionResult],
    Field(discriminator="status"),
]


class ChamferJobs(BaseModel):
    jobs: list[ChamferJob]

    def process(self) -> ChamferJobsResult:
        results = [job.process() for job in self.jobs]
        return ChamferJobsResult(results=results)


class ChamferJobsResult(BaseModel):
    results: list[ChamferResult]


def merge_bodies(src: Path, dst: Path, min_vertices: int = 10) -> None:
    """Boolean-union all significant bodies in an STL into one watertight mesh.

    Multi-body STLs (e.g. arch + letter labels) lose the smaller bodies
    during scan-to-model. This fuses them into a single solid so they
    survive all downstream processing.
    """
    mesh = trimesh.load_mesh(str(src))
    bodies = mesh.split(only_watertight=False)
    real_bodies = [b for b in bodies if b.vertices.shape[0] >= min_vertices]

    if len(real_bodies) <= 1:
        shutil.copy2(src, dst)
        return

    # Repair all bodies before boolean union
    for b in real_bodies:
        trimesh.repair.fix_normals(b)
        trimesh.repair.fill_holes(b)
        trimesh.repair.fix_winding(b)

    result = real_bodies[0]
    failed_bodies = []
    for i, b in enumerate(real_bodies[1:], 1):
        try:
            result = result.union(b)
        except Exception:
            # Second attempt: use convex hull of the label (always watertight)
            try:
                result = result.union(b.convex_hull)
                logger.debug(
                    "Union failed for body %d in %s, used convex hull instead",
                    i, src.name,
                )
            except Exception:
                failed_bodies.append(i)
                logger.debug(
                    "Union failed for body %d in %s (even with convex hull)",
                    i, src.name,
                )

    if failed_bodies:
        logger.info(
            "%s: %d/%d label bodies could not be merged",
            src.name, len(failed_bodies), len(real_bodies) - 1,
        )

    result.export(str(dst))
    logger.debug(
        "Merged %d bodies in %s (boolean union, %d fragments dropped)",
        len(real_bodies),
        src.name,
        len(bodies) - len(real_bodies),
    )


async def chamfer_models(
    filenames: list[str],
    input_dir: Path,
    output_dir: Path,
    config: ChamferConfig,
) -> None:
    """Chamfer models. Input files should already be merged (single body)."""
    stl_files = [f for f in filenames if f.casefold().endswith(".stl")]
    if not stl_files:
        return

    pairs = [(input_dir / f, output_dir / f) for f in stl_files]

    jobs = ChamferJobs(
        jobs=[
            ChamferJob(
                input_path=src,
                output_path=dst,
                height=config.height_mm,
                leg_depth=config.leg_depth_mm,
            )
            for src, dst in pairs
        ]
    )

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "formlabsAFA.mesh.chamfer",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(jobs.model_dump_json().encode()), timeout=60
    )
    results = ChamferJobsResult.model_validate_json(stdout)

    for filename, result in zip(stl_files, results.results):
        if isinstance(result, ChamferExceptionResult):
            raise RuntimeError(f"Failed to chamfer {filename}: {result.message}")
        logger.debug("Chamfered %s", filename)


if __name__ == "__main__":
    data = sys.stdin.buffer.read()
    print(ChamferJobs.model_validate_json(data).process().model_dump_json())
