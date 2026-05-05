from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .evidence import EvidenceStore, StageResult


def render_release_gate_json(
    *,
    stage_results: list[StageResult],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    ship = all(result.status == "pass" for result in stage_results)
    return {
        "ship": ship,
        "metadata": metadata,
        "stages": [asdict(result) for result in stage_results],
    }


def render_verdict(
    *,
    stage_results: list[StageResult],
    metadata: dict[str, Any],
) -> str:
    ship = all(result.status == "pass" for result in stage_results)
    lines = [
        f"SHIP: {'yes' if ship else 'no'}",
        "",
        "# Release Gate Verdict",
        "",
        f"- Git commit: `{metadata.get('git_commit', 'unknown')}`",
        f"- Dataset: `{metadata.get('dataset_path', 'unknown')}`",
        f"- STL count: `{metadata.get('stl_count', 'unknown')}`",
        f"- PreForm URL: `{metadata.get('preform_url', 'unknown')}`",
        "",
        "| Stage | Status | Duration | Artifacts |",
        "| --- | --- | ---: | --- |",
    ]
    for result in stage_results:
        artifacts = ", ".join(f"`{item}`" for item in result.artifacts) or "-"
        lines.append(
            f"| {result.stage} | {result.status} | {result.duration_seconds:.2f}s | {artifacts} |"
        )
    notes = [
        f"- {result.stage}: {note}"
        for result in stage_results
        for note in result.notes
    ]
    if notes:
        lines.extend(["", "## Notes", "", *notes])
    return "\n".join(lines) + "\n"


def write_verdict(
    store: EvidenceStore,
    *,
    stage_results: list[StageResult],
    metadata: dict[str, Any],
) -> None:
    store.write_json(
        "release-gate.json",
        render_release_gate_json(stage_results=stage_results, metadata=metadata),
    )
    store.write_text(
        "verdict.md",
        render_verdict(stage_results=stage_results, metadata=metadata),
    )
