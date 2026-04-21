from __future__ import annotations

from ..schemas import (
    BuildManifest,
    BuildManifestImportGroup,
    CasePackProfile,
    ClassificationRow,
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


def _case_profile(case_id: str, rows: list[ClassificationRow]) -> CasePackProfile:
    preset_names = sorted({row.preset for row in rows if row.preset})
    compatibility_key = build_compatibility_key(preset_names)
    total_xy = sum(_row_xy_area(row) * _support_factor(row.preset or "") for row in rows)
    difficulty = max(_row_xy_area(row) for row in rows) + total_xy
    preset_groups: dict[str, list[int]] = {}

    for row in rows:
        preset_name = row.preset
        if preset_name is None or row.row_id is None:
            continue
        preset_groups.setdefault(preset_name, []).append(row.row_id)

    return CasePackProfile(
        case_id=case_id,
        compatibility_key=compatibility_key,
        preset_groups=preset_groups,
        total_xy_footprint=total_xy,
        difficulty_score=difficulty,
        file_count=len(rows),
    )


def _group_case_profiles(rows: list[ClassificationRow]) -> list[CasePackProfile]:
    rows_by_case: dict[str, list[ClassificationRow]] = {}
    for row in rows:
        case_id = row.case_id or ""
        rows_by_case.setdefault(case_id, []).append(row)
    return [
        _case_profile(case_id, case_rows)
        for case_id, case_rows in rows_by_case.items()
        if case_id
    ]


def _group_profiles_by_compatibility(
    profiles: list[CasePackProfile],
) -> dict[str, list[CasePackProfile]]:
    grouped: dict[str, list[CasePackProfile]] = {}
    for profile in profiles:
        grouped.setdefault(profile.compatibility_key, []).append(profile)
    return grouped


def _build_manifest(compatibility_key: str, profiles: list[CasePackProfile]) -> BuildManifest:
    import_groups: dict[str, list[int]] = {}
    preset_names: list[str] = []

    for profile in profiles:
        for preset_name, row_ids in profile.preset_groups.items():
            preset_names.append(preset_name)
            import_groups.setdefault(preset_name, []).extend(row_ids)

    return BuildManifest(
        compatibility_key=compatibility_key,
        case_ids=[profile.case_id for profile in profiles],
        preset_names=sorted(set(preset_names)),
        import_groups=[
            BuildManifestImportGroup(
                preset_name=preset_name,
                preform_hint=get_preform_preset_hint(preset_name),
                row_ids=row_ids,
            )
            for preset_name, row_ids in sorted(import_groups.items())
        ],
    )


def plan_build_manifests(rows: list[ClassificationRow]) -> list[BuildManifest]:
    ready_rows = [
        row for row in rows if row.status == "Ready" and row.preset and row.case_id
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

            fillers = sorted(remaining, key=lambda profile: (profile.total_xy_footprint, profile.case_id))
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
