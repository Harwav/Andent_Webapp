"""Preset catalog tests for compatibility-aware build planning."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.preset_catalog import (
    PRESET_CATALOG,
    PresetProfile,
    build_compatibility_key,
    get_printer_xy_budget,
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


def test_get_printer_xy_budget_uses_live_form4bl_platform_budget():
    form4bl_budget = get_printer_xy_budget("Form 4BL")
    form4b_budget = get_printer_xy_budget("Form 4B")

    assert form4bl_budget == 69188.0
    assert form4b_budget == 25000.0


def test_get_printer_xy_budget_fails_closed_for_unknown_printer():
    assert get_printer_xy_budget("Unknown Printer") == 10820.9


def test_get_printer_xy_budget_fails_closed_for_missing_printer_name():
    assert get_printer_xy_budget(None) == 10820.9
    assert get_printer_xy_budget("") == 10820.9


def test_get_preform_preset_hint_maps_ui_preset_to_preform_hint():
    assert get_preform_preset_hint("Die - Flat, No Supports") == "die_v1"


def test_get_preset_profile_resolves_legacy_model_type_aliases():
    profile = get_preset_profile("Die")

    assert profile is not None
    assert profile.preset_name == "Die - Flat, No Supports"


def test_presets_are_compatible_is_false_for_unknown_preset():
    assert presets_are_compatible(["Tooth - With Supports", "Unknown Preset"]) is False


def test_presets_are_compatible_is_false_for_incompatible_presets(monkeypatch):
    monkeypatch.setitem(
        PRESET_CATALOG,
        "Experimental Preset",
        PresetProfile(
            preset_name="Experimental Preset",
            printer="Form 4BL",
            resin="Precision Model Resin",
            layer_height_microns=50,
            requires_supports=False,
            preform_hint="experimental_v1",
        ),
    )

    assert presets_are_compatible(
        ["Tooth - With Supports", "Experimental Preset"]
    ) is False


def test_build_compatibility_key_raises_for_unknown_preset():
    with pytest.raises(ValueError, match="unknown preset"):
        build_compatibility_key(["Tooth - With Supports", "Unknown Preset"])


def test_build_compatibility_key_raises_for_incompatible_presets(monkeypatch):
    monkeypatch.setitem(
        PRESET_CATALOG,
        "Experimental Preset",
        PresetProfile(
            preset_name="Experimental Preset",
            printer="Form 4BL",
            resin="Precision Model Resin",
            layer_height_microns=50,
            requires_supports=False,
            preform_hint="experimental_v1",
        ),
    )

    with pytest.raises(ValueError, match="compatible"):
        build_compatibility_key(["Tooth - With Supports", "Experimental Preset"])
