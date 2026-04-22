from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PresetProfile:
    preset_name: str
    printer: str
    resin: str
    layer_height_microns: int
    requires_supports: bool
    preform_hint: str | None


PRESET_CATALOG: dict[str, PresetProfile] = {
    "Ortho Solid - Flat, No Supports": PresetProfile(
        preset_name="Ortho Solid - Flat, No Supports",
        printer="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="ortho_solid_v1",
    ),
    "Ortho Hollow - Flat, No Supports": PresetProfile(
        preset_name="Ortho Hollow - Flat, No Supports",
        printer="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="ortho_hollow_v1",
    ),
    "Die - Flat, No Supports": PresetProfile(
        preset_name="Die - Flat, No Supports",
        printer="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="die_v1",
    ),
    "Tooth - With Supports": PresetProfile(
        preset_name="Tooth - With Supports",
        printer="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
        requires_supports=True,
        preform_hint="tooth_v1",
    ),
    "Splint - Flat, No Supports": PresetProfile(
        preset_name="Splint - Flat, No Supports",
        printer="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="splint_v1",
    ),
    "Antagonist Solid - Flat, No Supports": PresetProfile(
        preset_name="Antagonist Solid - Flat, No Supports",
        printer="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="antagonist_solid_v1",
    ),
    "Antagonist Hollow - Flat, No Supports": PresetProfile(
        preset_name="Antagonist Hollow - Flat, No Supports",
        printer="Form 4BL",
        resin="Precision Model Resin",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="antagonist_hollow_v1",
    ),
}

LEGACY_PRESET_ALIASES: dict[str, str] = {
    "Ortho - Solid": "Ortho Solid - Flat, No Supports",
    "Ortho - Hollow": "Ortho Hollow - Flat, No Supports",
    "Die": "Die - Flat, No Supports",
    "Tooth": "Tooth - With Supports",
    "Splint": "Splint - Flat, No Supports",
    "Antagonist": "Ortho Solid - Flat, No Supports",
    "Antagonist - Solid": "Antagonist Solid - Flat, No Supports",
    "Antagonist - Hollow": "Antagonist Hollow - Flat, No Supports",
}


def resolve_preset_name(preset_name: str | None) -> str | None:
    if preset_name is None:
        return None
    return LEGACY_PRESET_ALIASES.get(preset_name, preset_name)


def get_preset_profile(preset_name: str | None) -> PresetProfile | None:
    resolved_name = resolve_preset_name(preset_name)
    if resolved_name is None:
        return None
    return PRESET_CATALOG.get(resolved_name)


def get_preform_preset_hint(preset_name: str | None) -> str | None:
    profile = get_preset_profile(preset_name)
    return profile.preform_hint if profile else None


def build_compatibility_key(preset_names: list[str]) -> str:
    profiles = [get_preset_profile(name) for name in preset_names]
    if not profiles or any(profile is None for profile in profiles):
        raise ValueError("Cannot build compatibility key for unknown preset.")
    compatibility_values = {
        (profile.printer, profile.resin, profile.layer_height_microns)
        for profile in profiles
        if profile is not None
    }
    if len(compatibility_values) != 1:
        raise ValueError("Cannot build compatibility key for incompatible presets.")
    printer, resin, layer_height_microns = compatibility_values.pop()
    return (
        f"{printer.lower().replace(' ', '-')}|"
        f"{resin.lower().replace(' ', '-')}|"
        f"{layer_height_microns}"
    )


def presets_are_compatible(preset_names: list[str]) -> bool:
    profiles = [get_preset_profile(name) for name in preset_names]
    if not profiles or any(profile is None for profile in profiles):
        return False
    printer_resin_layer = {
        (profile.printer, profile.resin, profile.layer_height_microns)
        for profile in profiles
        if profile is not None
    }
    return len(printer_resin_layer) == 1
