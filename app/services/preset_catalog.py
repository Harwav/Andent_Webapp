from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace


SUPPORTED_PRINTER_GROUPS = ("Form 4BL", "Form 4B")
_MACHINE_TYPES = {
    "Form 4BL": "FRML-4-0",
    "Form 4B": "FORM-4-0",
}
_MATERIAL_CODES = {
    "Precision Model V1": "FLPMBE01",
    "LT Clear V2": "FLDLCL02",
}


@dataclass(frozen=True)
class PresetProfile:
    preset_name: str
    printer: str
    layer_height_microns: int
    requires_supports: bool
    preform_hint: str | None
    material_label: str | None = None
    material_code: str | None = None
    machine_type: str | None = None
    print_setting: str = "DEFAULT"
    also_valid_printers: tuple[str, ...] = ()
    resin: str | None = None

    def __post_init__(self) -> None:
        material_label = self.material_label or self.resin
        if material_label is None:
            material_label = "Precision Model V1"
        object.__setattr__(self, "material_label", material_label)
        object.__setattr__(self, "resin", material_label)
        object.__setattr__(
            self,
            "material_code",
            self.material_code or _MATERIAL_CODES.get(material_label),
        )
        object.__setattr__(
            self,
            "machine_type",
            self.machine_type or _MACHINE_TYPES.get(self.printer),
        )


PRESET_CATALOG: dict[str, PresetProfile] = {
    "Ortho Solid - Flat, No Supports": PresetProfile(
        preset_name="Ortho Solid - Flat, No Supports",
        printer="Form 4BL",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="ortho_solid_v1",
        material_label="Precision Model V1",
        material_code="FLPMBE01",
        also_valid_printers=("Form 4B",),
    ),
    "Ortho Hollow - Flat, No Supports": PresetProfile(
        preset_name="Ortho Hollow - Flat, No Supports",
        printer="Form 4BL",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="ortho_hollow_v1",
        material_label="Precision Model V1",
        material_code="FLPMBE01",
        also_valid_printers=("Form 4B",),
    ),
    "Die - Flat, No Supports": PresetProfile(
        preset_name="Die - Flat, No Supports",
        printer="Form 4BL",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="die_v1",
        material_label="Precision Model V1",
        material_code="FLPMBE01",
        also_valid_printers=("Form 4B",),
    ),
    "Tooth - With Supports": PresetProfile(
        preset_name="Tooth - With Supports",
        printer="Form 4BL",
        layer_height_microns=100,
        requires_supports=True,
        preform_hint="tooth_v1",
        material_label="Precision Model V1",
        material_code="FLPMBE01",
        also_valid_printers=("Form 4B",),
    ),
    "Splint - Flat, No Supports": PresetProfile(
        preset_name="Splint - Flat, No Supports",
        printer="Form 4BL",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="splint_v1",
        material_label="LT Clear V2",
        material_code="FLDLCL02",
        also_valid_printers=("Form 4B",),
    ),
    "Antagonist Solid - Flat, No Supports": PresetProfile(
        preset_name="Antagonist Solid - Flat, No Supports",
        printer="Form 4BL",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="antagonist_solid_v1",
        material_label="Precision Model V1",
        material_code="FLPMBE01",
        also_valid_printers=("Form 4B",),
    ),
    "Antagonist Hollow - Flat, No Supports": PresetProfile(
        preset_name="Antagonist Hollow - Flat, No Supports",
        printer="Form 4BL",
        layer_height_microns=100,
        requires_supports=False,
        preform_hint="antagonist_hollow_v1",
        material_label="Precision Model V1",
        material_code="FLPMBE01",
        also_valid_printers=("Form 4B",),
    ),
}

_PRINTER_BUILD_AREAS_MM2: dict[str, float] = {
    "Form 4": 200.0 * 125.0,
    "Form 4B": 200.0 * 125.0,
    "Form 4L": 335.0 * 200.0,
    "Form 4BL": 353.0 * 196.0,
}
_PRINTER_XY_BUDGETS_MM2: dict[str, float] = {
    "Form 4": 10820.9,
    "Form 4B": _PRINTER_BUILD_AREAS_MM2["Form 4B"],
    "Form 4L": 29000.0,
    "Form 4BL": _PRINTER_BUILD_AREAS_MM2["Form 4BL"],
}
_DEFAULT_XY_BUDGET_MM2 = min(_PRINTER_XY_BUDGETS_MM2.values())

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


def get_preset_profile(
    preset_name: str | None,
    printer_group: str | None = None,
) -> PresetProfile | None:
    resolved_name = resolve_preset_name(preset_name)
    if resolved_name is None:
        return None
    profile = PRESET_CATALOG.get(resolved_name)
    if profile is None:
        return None
    if printer_group is None or printer_group == profile.printer:
        return profile
    if printer_group not in profile.also_valid_printers:
        return None
    return replace(
        profile,
        printer=printer_group,
        machine_type=_MACHINE_TYPES.get(printer_group),
        also_valid_printers=tuple(
            printer for printer in (profile.printer, *profile.also_valid_printers)
            if printer != printer_group
        ),
    )


def get_preform_preset_hint(preset_name: str | None) -> str | None:
    profile = get_preset_profile(preset_name)
    return profile.preform_hint if profile else None


def get_printer_xy_budget(printer_name: str | None) -> float:
    if not printer_name:
        return _DEFAULT_XY_BUDGET_MM2
    return _PRINTER_XY_BUDGETS_MM2.get(printer_name, _DEFAULT_XY_BUDGET_MM2)


def build_compatibility_key(
    preset_names: list[str],
    printer_group: str | None = None,
) -> str:
    profiles = [get_preset_profile(name, printer_group=printer_group) for name in preset_names]
    if not profiles or any(profile is None for profile in profiles):
        raise ValueError("Cannot build compatibility key for unknown preset.")
    compatibility_values = {
        (profile.printer, profile.material_label, profile.layer_height_microns)
        for profile in profiles
        if profile is not None
    }
    if len(compatibility_values) != 1:
        raise ValueError("Cannot build compatibility key for incompatible presets.")
    printer, material_label, layer_height_microns = compatibility_values.pop()
    return (
        f"{printer.lower().replace(' ', '-')}|"
        f"{material_label.lower().replace(' ', '-')}|"
        f"{layer_height_microns}"
    )


def presets_are_compatible(
    preset_names: list[str],
    printer_group: str | None = None,
) -> bool:
    profiles = [get_preset_profile(name, printer_group=printer_group) for name in preset_names]
    if not profiles or any(profile is None for profile in profiles):
        return False
    printer_resin_layer = {
        (profile.printer, profile.material_label, profile.layer_height_microns)
        for profile in profiles
        if profile is not None
    }
    return len(printer_resin_layer) == 1
