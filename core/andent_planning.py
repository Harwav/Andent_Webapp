import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .batch_optimizer import BatchOptimizer, DEFAULT_BUILD_PLATE, STLDimensions, get_stl_dimensions, get_stl_volume_ml
from andent_classification import (
    ArtifactClassification,
    STRUCTURE_HOLLOW,
    STRUCTURE_REVIEW,
    WORKFLOW_MANUAL_REVIEW,
    WORKFLOW_ORTHO_IMPLANT,
    WORKFLOW_ORTHO_TOOTH,
    WORKFLOW_SPLINT,
    WORKFLOW_STANDARD,
    WORKFLOW_TOOTH_MODEL,
    classify_artifact,
    measure_mesh_thickness_stats,
    resolve_ortho_structure,
)

STANDARD_WORKFLOW_MODE = "standard"
ANDENT_V2_WORKFLOW_MODE = "andent_v2"
LEGACY_ANDENT_MVP_WORKFLOW_MODE = "andent_mvp"


@dataclass
class ResolvedWorkflowPolicy:
    workflow: str
    display_name: str
    approval_only: bool
    build_family: str = WORKFLOW_STANDARD
    requires_supports: bool = False
    approval_artifacts: Tuple[str, ...] = ("form",)
    save_form_artifact: bool = False
    save_screenshot_artifact: bool = False
    api_params_override: Dict[str, object] = field(default_factory=dict)
    scene_payload_override: Dict[str, object] = field(default_factory=dict)
    support_payload_override: Dict[str, object] = field(default_factory=dict)
    required_material_label: Optional[str] = None
    required_layer_thickness_mm: Optional[float] = None
    orientation_mode: Optional[str] = None
    tilt_degrees: Optional[float] = None
    requires_support_touchpoint_guard: bool = False
    review_reason: Optional[str] = None

    @property
    def scene_import_signature(self) -> Tuple[object, ...]:
        return (
            self.build_family,
            self.required_material_label,
            self.required_layer_thickness_mm,
            tuple(sorted(self.api_params_override.items())),
            tuple(sorted(self.scene_payload_override.items())),
        )


@dataclass
class BuildPlan:
    build_id: str
    workflow: str
    case_ids: List[str]
    file_paths: List[str]
    folder_paths: List[str]
    policy: ResolvedWorkflowPolicy
    dimensions_complete: bool = False
    dimensions: List[STLDimensions] = field(default_factory=list)
    contains_ortho: bool = False
    contains_tooth: bool = False
    tooth_model_count: int = 0
    case_file_map: Dict[str, List[str]] = field(default_factory=dict)
    file_workflows: Dict[str, str] = field(default_factory=dict)
    split_reasons: Dict[str, str] = field(default_factory=dict)

    @property
    def workflow_token(self) -> str:
        if self.workflow == WORKFLOW_SPLINT:
            return WORKFLOW_SPLINT
        if self.contains_ortho and self.contains_tooth:
            return "ortho-tooth"
        if self.contains_tooth:
            return "tooth"
        return "ortho"

    def build_job_name(self, date_token: str) -> str:
        case_ids = "+".join(sorted(self.case_ids)) if self.case_ids else self.build_id
        return f"{date_token}_{self.workflow_token}_{case_ids}"


@dataclass
class ManualReviewItem:
    case_id: str
    file_paths: List[str]
    reason: str
    workflow: str = WORKFLOW_MANUAL_REVIEW


@dataclass
class _CaseCandidate:
    case_id: str
    workflow: str
    file_paths: List[str]
    folder_paths: List[str]
    policy: ResolvedWorkflowPolicy
    dimensions: List[STLDimensions]
    dimensions_complete: bool
    contains_ortho: bool
    contains_tooth: bool
    tooth_model_count: int
    file_workflows: Dict[str, str]


def is_andent_v2_workflow_mode(workflow_mode: Optional[str]) -> bool:
    return workflow_mode in {ANDENT_V2_WORKFLOW_MODE, LEGACY_ANDENT_MVP_WORKFLOW_MODE}


def _manual_review_policy(reason: str) -> ResolvedWorkflowPolicy:
    return ResolvedWorkflowPolicy(
        workflow=WORKFLOW_MANUAL_REVIEW,
        display_name="Manual Review",
        approval_only=True,
        build_family=WORKFLOW_MANUAL_REVIEW,
        review_reason=reason,
    )


def _precision_model_policy(
    workflow: str,
    display_name: str,
    requires_supports: bool,
    *,
    hollow: bool = False,
) -> ResolvedWorkflowPolicy:
    return ResolvedWorkflowPolicy(
        workflow=workflow,
        display_name=display_name,
        approval_only=False,
        build_family=WORKFLOW_ORTHO_TOOTH,
        requires_supports=requires_supports,
        approval_artifacts=("form", "screenshot"),
        save_form_artifact=True,
        save_screenshot_artifact=True,
        api_params_override={
            "allow_overlapping_supports": False,
            "hollow": hollow,
        },
        scene_payload_override={"layer_thickness_mm": 0.05},
        required_material_label="Precision Model",
        required_layer_thickness_mm=0.05,
        support_payload_override={
            "density": 1.0,
            "raft_type": "FULL_RAFT",
            "raft_label_enabled": True,
            "touchpoint_size_mm": 0.5,
        } if requires_supports else {},
    )


def _resolve_group_ortho_structure(
    classifications: Sequence[ArtifactClassification],
) -> Tuple[Optional[str], Optional[str]]:
    ortho_resolutions = []
    for item in classifications:
        if item.workflow != WORKFLOW_ORTHO_IMPLANT:
            continue
        resolution = resolve_ortho_structure(
            item,
            dims=item.dimensions,
            volume_ml=get_stl_volume_ml(item.file_path),
            thickness_stats=measure_mesh_thickness_stats(item.file_path),
        )
        if resolution is not None:
            ortho_resolutions.append(resolution)

    if not ortho_resolutions:
        return None, None

    if any(item.structure == STRUCTURE_REVIEW for item in ortho_resolutions):
        return None, "Ortho geometry is borderline or incomplete, so solid/hollow needs review."

    structures = {item.structure for item in ortho_resolutions}
    if len(structures) > 1:
        return None, "Mixed solid and hollow ortho geometry cannot be resolved safely for a shared import."

    return next(iter(structures)), None


def resolve_workflow_policy(classifications: Sequence[ArtifactClassification]) -> ResolvedWorkflowPolicy:
    if not classifications:
        return _manual_review_policy("No classified artifacts were available for this case.")

    review_reasons = [item.review_reason for item in classifications if item.review_required and item.review_reason]
    if review_reasons:
        return _manual_review_policy("; ".join(review_reasons))

    workflows = {item.workflow for item in classifications}
    if WORKFLOW_SPLINT in workflows and len(workflows) > 1:
        return _manual_review_policy(
            "Mixed splint and model artifacts must be split before workflow policy resolution."
        )

    if workflows == {WORKFLOW_TOOTH_MODEL}:
        return _precision_model_policy(
            workflow=WORKFLOW_TOOTH_MODEL,
            display_name="Tooth Build",
            requires_supports=True,
        )

    if workflows == {WORKFLOW_SPLINT}:
        return ResolvedWorkflowPolicy(
            workflow=WORKFLOW_SPLINT,
            display_name="Splint Build",
            approval_only=False,
            build_family=WORKFLOW_SPLINT,
            requires_supports=True,
            approval_artifacts=("form", "screenshot"),
            save_form_artifact=True,
            save_screenshot_artifact=True,
            api_params_override={"hollow": False},
            support_payload_override={
                "density": 1.0,
                "raft_type": "FULL_RAFT",
                "raft_label_enabled": True,
                "touchpoint_size_mm": 0.5,
                "internal_supports_enabled": True,
            },
            required_material_label="LT Clear V2",
            required_layer_thickness_mm=0.1,
            orientation_mode="dental_tilted",
            tilt_degrees=15.0,
            requires_support_touchpoint_guard=True,
        )

    if workflows == {WORKFLOW_ORTHO_IMPLANT, WORKFLOW_TOOTH_MODEL}:
        ortho_structure, structure_review_reason = _resolve_group_ortho_structure(classifications)
        if structure_review_reason:
            return _manual_review_policy(structure_review_reason)
        if ortho_structure == STRUCTURE_HOLLOW:
            return _manual_review_policy(
                "Mixed ortho and tooth artifacts require review when the ortho model resolves hollow, "
                "because the current scene import settings are shared across the build."
            )
        return _precision_model_policy(
            workflow=WORKFLOW_ORTHO_TOOTH,
            display_name="Ortho / Tooth Build",
            requires_supports=True,
        )

    if workflows == {WORKFLOW_ORTHO_IMPLANT}:
        ortho_structure, structure_review_reason = _resolve_group_ortho_structure(classifications)
        if structure_review_reason:
            return _manual_review_policy(structure_review_reason)
        return _precision_model_policy(
            workflow=WORKFLOW_ORTHO_IMPLANT,
            display_name="Ortho Build",
            requires_supports=False,
            hollow=ortho_structure == STRUCTURE_HOLLOW,
        )

    return _precision_model_policy(
        workflow=WORKFLOW_ORTHO_IMPLANT,
        display_name="Ortho Build",
        requires_supports=False,
    )


def plan_andent_builds(
    file_paths: Iterable[str],
    build_plate: Tuple[float, float] = DEFAULT_BUILD_PLATE,
    spacing_mm: float = 0.5,
    max_batch_size: int = 10,
    fit_probe: Optional[Callable[[BuildPlan, _CaseCandidate], Tuple[bool, Optional[str]]]] = None,
) -> Tuple[List[BuildPlan], List[ManualReviewItem]]:
    optimizer = BatchOptimizer(
        build_plate=build_plate,
        spacing_mm=spacing_mm,
        max_batch_size=max_batch_size,
        depth_tolerance=1.10,  # PreForm's 3D layout packs ~10% tighter than our 2D shelf estimate
    )
    by_case: Dict[str, List[ArtifactClassification]] = {}
    manual_reviews: List[ManualReviewItem] = []

    for file_path in sorted(file_paths):
        classification = classify_artifact(file_path)
        if classification.dimensions is None:
            classification.dimensions = get_stl_dimensions(file_path)
        if classification.dimensions is None:
            manual_reviews.append(
                ManualReviewItem(
                    case_id=classification.case_id or "UNASSIGNED",
                    file_paths=[file_path],
                    reason="Could not determine model dimensions to verify build fit safely.",
                )
            )
            continue
        if classification.review_required or not classification.case_id:
            manual_reviews.append(
                ManualReviewItem(
                    case_id=classification.case_id or "UNASSIGNED",
                    file_paths=[file_path],
                    reason=classification.review_reason or "Manual review required.",
                )
            )
            continue
        by_case.setdefault(classification.case_id, []).append(classification)

    case_candidates: List[_CaseCandidate] = []
    for case_id, classifications in sorted(by_case.items()):
        candidate_groups: List[List[ArtifactClassification]] = []
        grouped_workflows = {item.workflow for item in classifications}
        if WORKFLOW_SPLINT in grouped_workflows and len(grouped_workflows) > 1:
            candidate_groups.append([item for item in classifications if item.workflow == WORKFLOW_SPLINT])
            candidate_groups.append([item for item in classifications if item.workflow != WORKFLOW_SPLINT])
        else:
            candidate_groups.append(list(classifications))

        for candidate_group in candidate_groups:
            policy = resolve_workflow_policy(candidate_group)
            if policy.review_reason:
                manual_reviews.append(
                    ManualReviewItem(
                        case_id=case_id,
                        file_paths=[item.file_path for item in candidate_group],
                        reason=policy.review_reason,
                        workflow=policy.workflow,
                    )
                )
                continue

            dimensions = [item.dimensions for item in candidate_group if item.dimensions is not None]
            dimensions_complete = len(dimensions) == len(candidate_group)
            candidate = _CaseCandidate(
                case_id=case_id,
                workflow=policy.workflow,
                file_paths=[item.file_path for item in candidate_group],
                folder_paths=sorted({os.path.dirname(item.file_path) for item in candidate_group}),
                policy=policy,
                dimensions=dimensions,
                dimensions_complete=dimensions_complete,
                contains_ortho=any(item.workflow == WORKFLOW_ORTHO_IMPLANT for item in candidate_group),
                contains_tooth=any(item.workflow == WORKFLOW_TOOTH_MODEL for item in candidate_group),
                tooth_model_count=sum(1 for item in candidate_group if item.workflow == WORKFLOW_TOOTH_MODEL),
                file_workflows={item.file_path: item.workflow for item in candidate_group},
            )

            if len(candidate.file_paths) > max_batch_size:
                manual_reviews.append(
                    ManualReviewItem(
                        case_id=case_id,
                        file_paths=candidate.file_paths,
                        reason="Case exceeds the maximum files allowed on a single build.",
                        workflow=policy.workflow,
                    )
                )
                continue

            if candidate.dimensions_complete and not optimizer._can_pack_batch(candidate.dimensions):
                manual_reviews.append(
                    ManualReviewItem(
                        case_id=case_id,
                        file_paths=candidate.file_paths,
                        reason="Case does not fit on one build plate without splitting.",
                        workflow=policy.workflow,
                    )
                )
                continue

            case_candidates.append(candidate)

    build_plans: List[BuildPlan] = []
    build_index = 1

    for build_family in (WORKFLOW_ORTHO_TOOTH, WORKFLOW_SPLINT):
        workflow_cases = [candidate for candidate in case_candidates if candidate.policy.build_family == build_family]
        workflow_cases.sort(key=lambda candidate: (-len(candidate.file_paths), candidate.case_id))
        active_builds: List[BuildPlan] = []

        for candidate in workflow_cases:
            placed = False
            rejection_reasons: List[str] = []
            for build in active_builds:
                if build.policy.build_family != candidate.policy.build_family:
                    continue
                if build.policy.scene_import_signature != candidate.policy.scene_import_signature:
                    rejection_reasons.append(
                        f"{build.build_id}: scene import signature mismatch"
                    )
                    continue
                if len(build.file_paths) + len(candidate.file_paths) > max_batch_size:
                    rejection_reasons.append(
                        f"{build.build_id}: max file-count cap would be exceeded"
                    )
                    continue

                if build.dimensions_complete and candidate.dimensions_complete:
                    if not optimizer._can_pack_batch(build.dimensions + candidate.dimensions):
                        if fit_probe:
                            probe_ok, probe_reason = fit_probe(build, candidate)
                            if not probe_ok:
                                rejection_reasons.append(
                                    f"{build.build_id}: {probe_reason or 'scene-fit probe rejected merge'}"
                                )
                                continue
                        else:
                            rejection_reasons.append(
                                f"{build.build_id}: heuristic fit rejection"
                            )
                            continue
                elif build.case_ids:
                    rejection_reasons.append(
                        f"{build.build_id}: dimensions incomplete for safe merge"
                    )
                    continue

                build.case_ids.append(candidate.case_id)
                build.file_paths.extend(candidate.file_paths)
                build.folder_paths = sorted(set(build.folder_paths + candidate.folder_paths))
                build.dimensions_complete = build.dimensions_complete and candidate.dimensions_complete
                build.dimensions.extend(candidate.dimensions)
                build.contains_ortho = build.contains_ortho or candidate.contains_ortho
                build.contains_tooth = build.contains_tooth or candidate.contains_tooth
                build.tooth_model_count += candidate.tooth_model_count
                build.case_file_map[candidate.case_id] = list(candidate.file_paths)
                build.file_workflows.update(candidate.file_workflows)
                build.policy.requires_supports = build.contains_tooth
                placed = True
                break

            if placed:
                continue

            new_build = BuildPlan(
                build_id=f"{build_family}-{build_index:03d}",
                workflow=candidate.workflow,
                case_ids=[candidate.case_id],
                file_paths=list(candidate.file_paths),
                folder_paths=list(candidate.folder_paths),
                policy=candidate.policy,
                dimensions_complete=candidate.dimensions_complete,
                dimensions=list(candidate.dimensions),
                contains_ortho=candidate.contains_ortho,
                contains_tooth=candidate.contains_tooth,
                tooth_model_count=candidate.tooth_model_count,
                case_file_map={candidate.case_id: list(candidate.file_paths)},
                file_workflows=dict(candidate.file_workflows),
                split_reasons={
                    candidate.case_id: "; ".join(rejection_reasons)
                } if rejection_reasons else {},
            )
            build_index += 1
            active_builds.append(new_build)

        build_plans.extend(active_builds)

    logging.info(
        "Andent planning produced %s build(s) and %s manual-review item(s).",
        len(build_plans),
        len(manual_reviews),
    )
    return build_plans, manual_reviews
