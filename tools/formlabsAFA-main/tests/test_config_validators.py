"""Smoke tests for config validators.

Run as a plain script (no pytest required):
    python -m tests.test_config_validators
"""
from __future__ import annotations

import sys
from pathlib import Path

from pydantic import ValidationError

from formlabsAFA.config import AppConfig


BASE_DICT = {
    "general": {"base_path": "/tmp/formlabsAFA"},
}


def _expect_valid(name: str, overrides: dict) -> None:
    data = {**BASE_DICT, **overrides}
    try:
        AppConfig.model_validate(data)
    except ValidationError as e:
        print(f"FAIL {name}: expected valid config but got ValidationError:\n{e}")
        sys.exit(1)
    print(f"PASS {name}")


def _expect_invalid(name: str, overrides: dict, needle: str) -> None:
    data = {**BASE_DICT, **overrides}
    try:
        AppConfig.model_validate(data)
    except ValidationError as e:
        if needle not in str(e):
            print(f"FAIL {name}: raised but message missing {needle!r}:\n{e}")
            sys.exit(1)
        print(f"PASS {name}")
        return
    print(f"FAIL {name}: expected ValidationError, got clean config")
    sys.exit(1)


def main() -> None:
    _expect_valid("defaults", {})

    _expect_invalid(
        "min_models > initial_batch_size",
        {"batch": {"initial_batch_size": 10, "min_models": 15}},
        "min_models",
    )

    _expect_invalid(
        "webbing mode with no connections and no rail",
        {
            "build": {"mode": "webbing"},
            "webbing": {
                "connect_front": False, "connect_back": False,
                "connect_left": False, "connect_right": False,
                "perimeter_rail": False,
            },
        },
        "no beams",
    )

    _expect_invalid(
        "fixture enabled with empty stl_path",
        {"fixture": {"enabled": True, "stl_path": ""}},
        "fixture.stl_path",
    )

    _expect_invalid(
        "bbox_fraction out of range",
        {"model_labels": {"enabled": True, "bbox_fraction": [0.5, 1.5, 0.5]}},
        "bbox_fraction",
    )

    _expect_invalid(
        "bbox_fraction wrong length",
        {"model_labels": {"bbox_fraction": [0.5, 1.0]}},
        "3 entries",
    )

    # Regression: ensure loose mode and frame mode also validate cleanly with defaults.
    _expect_valid("loose mode", {"build": {"mode": "loose"}})
    _expect_valid("frame mode", {"build": {"mode": "frame"}})
    _expect_valid(
        "webbing mode with at least one connection",
        {"build": {"mode": "webbing"}},
    )

    # Local config file should also parse cleanly.
    local_cfg = Path(__file__).parent.parent / "config.toml"
    if local_cfg.is_file():
        import tomllib
        with open(local_cfg, "rb") as f:
            data = tomllib.load(f)
        try:
            AppConfig.model_validate(data)
        except ValidationError as e:
            print(f"FAIL local config.toml: {e}")
            sys.exit(1)
        print("PASS local config.toml parses cleanly")

    print("\nAll validator smoke tests passed.")


if __name__ == "__main__":
    main()
