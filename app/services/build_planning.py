from __future__ import annotations

from ..schemas import (
    BuildManifest,
    BuildManifestImportGroup,
    CasePackProfile,
    ClassificationRow,
    FilePrepSpec,
)
from .preset_catalog import (
    build_compatibility_key,
    get_preform_preset_hint,
    get_preset_profile,
)


FORM4BL_XY_BUDGET = 29000.0
SUPPORT_INFLATION = 1.18


def _row_xy_area(row: ClassificationRow) -> float:
    if row.dimensions is None:
        return 0.0
    return float(row.dimensions.x_mm * row.dimensions.y_mm)


def _support_factor(preset_name: str) -> float:
    profile = get_preset_profile(preset_name)
    if profile is None:
        return 1.0
    return SUPPORT_INFLATION if profile.requires_supports else 1.0


def _row_file_path(row: ClassificationRow) -> str:
    return row.file_path or row.file_url or row.file_name


def _build_file_prep_spec(
    row: ClassificationRow,
    compatibility_key: str,
) -> FilePrepSpec | None:
    if row.row_id is None or row.case_id is None or row.preset is None:
        return None
    profile = get_preset_profile(row.preset)
    if profile is None:
        return None
    return FilePrepSpec(
        row_id=row.row_id,
        case_id=row.case_id,
        file_name=row.file_name,
        file_path=_row_file_path(row),
        preset_name=row.preset,
        compatibility_key=compatibility_key,
        xy_footprint_estimate=_row_xy_area(row),
        support_inflation_factor=_support_factor(row.preset),
        preform_hint=profile.preform_hint,
    )


def _case_profile(case_id: str, rows: list[ClassificationRow]) -> CasePackProfile | None:
    preset_names = sorted({row.preset for row in rows if row.preset})
    try:
        compatibility_key = build_compatibility_key(preset_names)
    except ValueError:
        return None

    total_xy = sum(_row_xy_area(row) * _support_factor(row.preset or "") for row in rows)
    difficulty = max(_row_xy_area(row) for row in rows) + total_xy
    file_specs: list[FilePrepSpec] = []

    for row in sorted(rows, key=lambda item: (item.row_id or 0, item.file_name)):
        spec = _build_file_prep_spec(row, compatibility_key)
        if spec is None:
            return None
        file_specs.append(spec)

    return CasePackProfile(
        case_id=case_id,
        compatibility_key=compatibility_key,
        file_specs=file_specs,
        total_xy_footprint=total_xy,
        difficulty_score=difficulty,
        file_count=len(rows),
    )


def _group_case_profiles(rows: list[ClassificationRow]) -> list[CasePackProfile]:
    rows_by_case: dict[str, list[ClassificationRow]] = {}
    for row in rows:
        case_id = row.case_id or ""
        rows_by_case.setdefault(case_id, []).append(row)
    profiles: list[CasePackProfile] = []
    for case_id, case_rows in rows_by_case.items():
        if not case_id:
            continue
        profile = _case_profile(case_id, case_rows)
        if profile is not None:
            profiles.append(profile)
    return profiles


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

    for profile in profiles:
        for spec in profile.file_specs:
            preset_names.append(spec.preset_name)
            import_groups.setdefault(spec.preset_name, []).append(spec)

    next_order = 0
    manifest_groups: list[BuildManifestImportGroup] = []
    for preset_name in sorted(import_groups):
        group_hint = get_preform_preset_hint(preset_name)
        ordered_files = sorted(
            import_groups[preset_name],
            key=lambda spec: (spec.case_id, spec.row_id, spec.file_name),
        )
        files = []
        for spec in ordered_files:
            files.append(
                spec.model_copy(
                    update={
                        "order": next_order,
                        "preform_hint": group_hint,
                    }
                )
            )
            next_order += 1
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


def plan_build_manifests(rows: list[ClassificationRow]) -> list[BuildManifest]:
    ready_rows = [
        row
        for row in rows
        if row.status == "Ready" and row.preset and row.case_id and row.row_id is not None
    ]
    cases = _group_case_profiles(ready_rows)
    manifests: list[BuildManifest] = []

    for compatibility_key, profiles in _group_profiles_by_compatibility(cases).items():
        remaining = sorted(
            profiles,
            key=lambda profile: (
                -profile.difficulty_score,
                -profile.total_xy_footprint,
                profile.case_id,
            ),
        )

        while remaining:
            seed = remaining.pop(0)
            chosen = [seed]
            used = seed.total_xy_footprint

            while remaining and used + remaining[0].total_xy_footprint <= FORM4BL_XY_BUDGET:
                candidate = remaining.pop(0)
                chosen.append(candidate)
                used += candidate.total_xy_footprint

            fillers = sorted(
                remaining,
                key=lambda profile: (profile.total_xy_footprint, profile.case_id),
            )
            for filler in list(fillers):
                if (
                    used + filler.total_xy_footprint <= FORM4BL_XY_BUDGET
                    and filler in remaining
                ):
                    chosen.append(filler)
                    used += filler.total_xy_footprint
                    remaining.remove(filler)

            manifests.append(_build_manifest(compatibility_key, chosen))

    return manifests
