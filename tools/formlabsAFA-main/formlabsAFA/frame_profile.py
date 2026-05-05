from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import trimesh

from formlabsAFA.config import LayoutBounds
from formlabsAFA.mesh.geometry import Box2D, center_mesh_xy, derive_frame_spanners

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger("formlabsAFA.frame_profile")


@dataclass
class FrameProfile:
    name: str
    stl_path: Path
    mesh: trimesh.Trimesh
    spanners: list[Box2D]
    layout_bounds: LayoutBounds
    min_models: int
    max_models: int
    priority: int = 0


def load_profile(profile_dir: Path, default_bounds: LayoutBounds) -> FrameProfile:
    toml_path = profile_dir / "profile.toml"
    stl_path = profile_dir / "frame.stl"

    if not toml_path.is_file():
        raise FileNotFoundError(f"Missing profile.toml in {profile_dir}")
    if not stl_path.is_file():
        raise FileNotFoundError(f"Missing frame.stl in {profile_dir}")

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    name = data.get("name", profile_dir.name)
    min_models = data.get("min_models", 1)
    max_models = data.get("max_models", 20)
    priority = data.get("priority", 0)

    if "layout_bounds" in data:
        bounds = LayoutBounds.model_validate(data["layout_bounds"])
    else:
        bounds = default_bounds

    mesh = center_mesh_xy(trimesh.load_mesh(stl_path))
    spanners = derive_frame_spanners(mesh, bounds)

    return FrameProfile(
        name=name,
        stl_path=stl_path,
        mesh=mesh,
        spanners=spanners,
        layout_bounds=bounds,
        min_models=min_models,
        max_models=max_models,
        priority=priority,
    )


def load_profiles(
    profiles_dir: Path, default_bounds: LayoutBounds
) -> dict[str, FrameProfile]:
    profiles: dict[str, FrameProfile] = {}
    if not profiles_dir.is_dir():
        logger.warning("Frame profiles directory not found: %s", profiles_dir)
        return profiles

    for child in sorted(profiles_dir.iterdir()):
        if child.is_dir() and (child / "profile.toml").is_file():
            try:
                profile = load_profile(child, default_bounds)
                profiles[profile.name] = profile
                logger.info(
                    "Loaded frame profile '%s' (models %d-%d)",
                    profile.name,
                    profile.min_models,
                    profile.max_models,
                )
            except Exception:
                logger.exception("Failed to load frame profile from %s", child)

    if not profiles:
        logger.warning("No frame profiles loaded from %s", profiles_dir)
    return profiles


def select_frame(
    profiles: dict[str, FrameProfile],
    model_count: int,
    large_model_count: int,
    large_frame_cutoff: int,
    min_large_models_small_frame: int,
) -> FrameProfile:
    candidates = []
    for profile in profiles.values():
        if profile.min_models <= model_count <= profile.max_models:
            candidates.append(profile)

    if not candidates:
        # Fall back: pick the profile with the highest max_models
        candidates = sorted(profiles.values(), key=lambda p: p.max_models, reverse=True)
        if not candidates:
            raise RuntimeError("No frame profiles available")
        return candidates[0]

    # Sort by priority (lower = preferred)
    candidates.sort(key=lambda p: p.priority)
    return candidates[0]
