"""Preset catalog tests for compatibility-aware build planning."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.preset_catalog import (
    build_compatibility_key,
    get_preform_preset_hint,
    get_preset_profile,
    presets_are_compatible,
)


def test_get_preset_profile_derives_form4bl_precision_defaults():
    profile = get_preset_profile("Tooth - With Supports")

    assert profile.preset_name == "Tooth - With Supports"
    assert profile.printer == "Form 4BL"
    assert profile.resin == "Precision Model Resin"
    assert profile.layer_height_microns == 100
    assert profile.requires_supports is True


def test_presets_are_compatible_when_printer_resin_and_layer_match():
    assert presets_are_compatible(
        ["Ortho Solid - Flat, No Supports", "Tooth - With Supports"]
    ) is True


def test_build_compatibility_key_is_stable_for_mixed_compatible_presets():
    key = build_compatibility_key(
        ["Tooth - With Supports", "Ortho Hollow - Flat, No Supports"]
    )

    assert key == "form-4bl|precision-model-resin|100"


def test_get_preform_preset_hint_maps_ui_preset_to_preform_hint():
    assert get_preform_preset_hint("Die - Flat, No Supports") == "die_v1"
