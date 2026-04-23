from __future__ import annotations

from ..schemas import (
    BuildManifest,
    BuildManifestImportGroup,
    CasePackProfile,
    ClassificationRow,
    DimensionSummary,
    FilePrepSpec,
)
from .preset_catalog import (
    build_compatibility_key,
    get_printer_xy_budget,
    get_preform_preset_hint,
    get_preset_profile,
    resolve_preset_name,
)
FULL_ARCH_MAX_SPAN_MM = 65.0
FULL_ARCH_MIN_SHORT_SIDE_MM = 55.0
FULL_ARCH_MIN_XY_AREA = 3400.0
FULL_ARCH_FACTOR = 0.58

ManifestOrderKey = tuple[float, float, str]


def _row_xy_area(row: ClassificationRow) -> float:
    if row.dimensions is None:
        return 0.0
    return float(row.dimensions.x_mm * row.dimensions.y_mm)


def _is_full_arch_dimensions(dimensions: DimensionSummary | None) -> bool:
    if dimensions is None:
        return False
    long_side = max(float(dimensions.x_mm), float(dimensions.y_mm))
    short_side = min(float(dimensions.x_mm), float(dimensions.y_mm))
    if long_side == 0.0:
        return False
    xy_area = float(dimensions.x_mm * dimensions.y_mm)
    minimum_arch_compactness = FULL_ARCH_MIN_SHORT_SIDE_MM / FULL_ARCH_MAX_SPAN_MM
    return (
        long_side >= FULL_ARCH_MAX_SPAN_MM
        and short_side >= FULL_ARCH_MIN_SHORT_SIDE_MM
        and xy_area >= FULL_ARCH_MIN_XY_AREA
        and (short_side / long_side) >= minimum_arch_compactness
    )


def _effective_row_xy_area(row: ClassificationRow) -> float:
    raw_xy = _row_xy_area(row)
    if raw_xy == 0.0:
        return 0.0
    profile = get_preset_profile(row.preset)
    if profile is not None and profile.printer == "Form 4BL" and _is_full_arch_dimensions(row.dimensions):
        return raw_xy * FULL_ARCH_FACTOR
    return raw_xy


def _canonical_preset_name(preset_name: str | None) -> str | None:
    profile = get_preset_profile(preset_name)
    if profile is not None:
        return profile.preset_name
    return resolve_preset_name(preset_name)


def _row_file_path(row: ClassificationRow) -> str | None:
    if row.file_path and row.file_path.strip():
        return row.file_path
    return None


def _build_file_prep_spec(
    row: ClassificationRow,
    compatibility_key: str,
) -> tuple[FilePrepSpec | None, str | None]:
    canonical_preset_name = _canonical_preset_name(row.preset)
    if row.row_id is None:
        return None, "missing_row_id"
    if row.case_id is None or canonical_preset_name is None:
        return None, None
    profile = get_preset_profile(canonical_preset_name)
    if profile is None:
        return None, None
    file_path = _row_file_path(row)
    if file_path is None:
        return None, "missing_file_path"
    return FilePrepSpec(
        row_id=row.row_id,
        case_id=row.case_id,
        file_name=row.file_name,
        file_path=file_path,
        preset_name=canonical_preset_name,
        compatibility_key=compatibility_key,
        xy_footprint_estimate=_effective_row_xy_area(row),
        support_inflation_factor=1.0,
        preform_hint=profile.preform_hint,
    ), None


def _build_non_plannable_manifest(
    *,
    case_id: str,
    preset_names: list[str],
    reason: str,
    compatibility_key: str | None = None,
) -> BuildManifest:
    return BuildManifest(
        compatibility_key=compatibility_key,
        case_ids=[case_id],
        preset_names=preset_names,
        import_groups=[],
        planning_status="non_plannable",
        non_plannable_reason=reason,
    )


def _case_metrics(rows: list[ClassificationRow]) -> tuple[float, float]:
    measurable_rows = [row for row in rows if row.dimensions is not None]
    total_xy = sum(_effective_row_xy_area(row) for row in measurable_rows)
    difficulty = max((_effective_row_xy_area(row) for row in measurable_rows), default=0.0) + total_xy
    return total_xy, difficulty


def _case_priority(case_id: str, rows: list[ClassificationRow]) -> ManifestOrderKey:
    total_xy, difficulty = _case_metrics(rows)
    return (-difficulty, -total_xy, case_id)


def _profile_priority(profile: CasePackProfile) -> tuple[float, float, str]:
    return (
        -profile.difficulty_score,
        -profile.total_xy_footprint,
        profile.case_id,
    )


def _case_profile(case_id: str, rows: list[ClassificationRow]) -> tuple[CasePackProfile | None, BuildManifest | None]:
    preset_names = sorted(
        {
            canonical_preset_name
            for row in rows
            if (canonical_preset_name := _canonical_preset_name(row.preset)) is not None
        }
    )

    try:
        compatibility_key = build_compatibility_key(preset_names)
    except ValueError:
        if any(get_preset_profile(name) is None for name in preset_names):
            return None, None
        return None, _build_non_plannable_manifest(
            case_id=case_id,
            preset_names=preset_names,
            reason="incompatible_case_presets",
        )

    if any(row.dimensions is None for row in rows):
        return None, _build_non_plannable_manifest(
            case_id=case_id,
            preset_names=preset_names,
            reason="missing_dimensions",
            compatibility_key=compatibility_key,
        )

    total_xy, difficulty = _case_metrics(rows)
    file_specs: list[FilePrepSpec] = []

    for row in sorted(rows, key=lambda item: (item.row_id or 0, item.file_name)):
        spec, failure_reason = _build_file_prep_spec(row, compatibility_key)
        if spec is None:
            if failure_reason is None:
                return None, None
            return None, _build_non_plannable_manifest(
                case_id=case_id,
                preset_names=preset_names,
                reason=failure_reason,
                compatibility_key=compatibility_key,
            )
        file_specs.append(spec)

    xy_budget = get_printer_xy_budget(
        get_preset_profile(preset_names[0]).printer if preset_names else None
    )

    if total_xy > xy_budget:
        return None, _build_non_plannable_manifest(
            case_id=case_id,
            preset_names=preset_names,
            reason="oversized_case",
            compatibility_key=compatibility_key,
        )

    return CasePackProfile(
        case_id=case_id,
        compatibility_key=compatibility_key,
        file_specs=file_specs,
        total_xy_footprint=total_xy,
        difficulty_score=difficulty,
        file_count=len(rows),
    ), None


def _group_case_profiles(
    rows: list[ClassificationRow],
) -> tuple[list[CasePackProfile], list[tuple[ManifestOrderKey, BuildManifest]]]:
    rows_by_case: dict[str, list[ClassificationRow]] = {}
    for row in rows:
        case_id = row.case_id or ""
        rows_by_case.setdefault(case_id, []).append(row)
    profiles: list[CasePackProfile] = []
    non_plannable_cases: list[tuple[ManifestOrderKey, BuildManifest]] = []
    for case_id, case_rows in rows_by_case.items():
        if not case_id:
            continue
        profile, non_plannable = _case_profile(case_id, case_rows)
        if profile is not None:
            profiles.append(profile)
        if non_plannable is not None:
            non_plannable_cases.append((_case_priority(case_id, case_rows), non_plannable))
    return profiles, non_plannable_cases


def _group_profiles_by_compatibility(
    profiles: list[CasePackProfile],
) -> dict[str, list[CasePackProfile]]:
    grouped: dict[str, list[CasePackProfile]] = {}
    for profile in profiles:
        grouped.setdefault(profile.compatibility_key, []).append(profile)
    return grouped


def _build_manifest(compatibility_key: str, profiles: list[CasePackProfile]) -> BuildManifest:
    import_groups: dict[str, list[FilePrepSpec]] = {}
    preset_names: list[str] = []
    order_by_row_id: dict[int, int] = {}
    next_order = 0

    for profile in profiles:
        for spec in profile.file_specs:
            preset_names.append(spec.preset_name)
            import_groups.setdefault(spec.preset_name, []).append(spec)
            order_by_row_id[spec.row_id] = next_order
            next_order += 1

    manifest_groups: list[BuildManifestImportGroup] = []
    for preset_name in sorted(import_groups):
        group_hint = get_preform_preset_hint(preset_name)
        ordered_files = sorted(
            import_groups[preset_name],
            key=lambda spec: order_by_row_id[spec.row_id],
        )
        files = []
        for spec in ordered_files:
            files.append(
                spec.model_copy(
                    update={
                        "order": order_by_row_id[spec.row_id],
                        "preform_hint": group_hint,
                    }
                )
            )
        manifest_groups.append(
            BuildManifestImportGroup(
                preset_name=preset_name,
                preform_hint=group_hint,
                row_ids=[spec.row_id for spec in files],
                files=files,
            )
        )

    return BuildManifest(
        compatibility_key=compatibility_key,
        case_ids=[profile.case_id for profile in profiles],
        preset_names=sorted(set(preset_names)),
        import_groups=manifest_groups,
    )


def _profile_xy_budget(profile: CasePackProfile) -> float:
    if not profile.file_specs:
        return get_printer_xy_budget(None)
    profile_details = get_preset_profile(profile.file_specs[0].preset_name)
    printer_name = profile_details.printer if profile_details is not None else None
    return get_printer_xy_budget(printer_name)


def _startup_case_count(profile: CasePackProfile) -> int:
    if not profile.file_specs:
        return 1
    profile_details = get_preset_profile(profile.file_specs[0].preset_name)
    printer_name = profile_details.printer if profile_details is not None else None
    if printer_name == "Form 4B":
        return 3
    if printer_name == "Form 4BL":
        return 8
    return 1


def _fits_with_profile(
    used_xy: float,
    candidate: CasePackProfile,
    xy_budget: float,
) -> bool:
    return used_xy + candidate.total_xy_footprint <= xy_budget


def plan_build_manifests(rows: list[ClassificationRow]) -> list[BuildManifest]:
    ready_rows = [
        row
        for row in rows
        if row.status == "Ready" and row.preset and row.case_id
    ]
    cases, non_plannable_cases = _group_case_profiles(ready_rows)
    ordered_manifests: list[tuple[ManifestOrderKey, BuildManifest]] = []
    remaining_by_compatibility = {
        compatibility_key: sorted(profiles, key=_profile_priority)
        for compatibility_key, profiles in _group_profiles_by_compatibility(cases).items()
    }

    while remaining_by_compatibility:
        compatibility_key, remaining = min(
            remaining_by_compatibility.items(),
            key=lambda item: _profile_priority(item[1][0]),
        )
        seed = remaining.pop(0)
        chosen = [seed]
        used = seed.total_xy_footprint
        xy_budget = _profile_xy_budget(seed)
        startup_case_count = _startup_case_count(seed)

        startup_candidates: list[CasePackProfile] = []
        if len(remaining) + 1 >= startup_case_count:
            startup_candidates = list(remaining[: startup_case_count - 1])

        for candidate in startup_candidates:
            if candidate in remaining and _fits_with_profile(used, candidate, xy_budget):
                chosen.append(candidate)
                used += candidate.total_xy_footprint
                remaining.remove(candidate)

        descending_failed = False
        for candidate in list(remaining):
            if _fits_with_profile(used, candidate, xy_budget):
                chosen.append(candidate)
                used += candidate.total_xy_footprint
                remaining.remove(candidate)
                continue
            descending_failed = True
            break

        if descending_failed:
            fillers = sorted(
                remaining,
                key=lambda profile: (profile.total_xy_footprint, profile.case_id),
            )
            for filler in list(fillers):
                if filler in remaining and _fits_with_profile(used, filler, xy_budget):
                    chosen.append(filler)
                    used += filler.total_xy_footprint
                    remaining.remove(filler)

        ordered_manifests.append(
            (_profile_priority(seed), _build_manifest(compatibility_key, chosen))
        )
        if not remaining:
            del remaining_by_compatibility[compatibility_key]

    ordered_manifests.extend(non_plannable_cases)
    ordered_manifests.sort(key=lambda item: item[0])
    return [manifest for _, manifest in ordered_manifests]
