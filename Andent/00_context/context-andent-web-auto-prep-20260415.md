## Task Statement

Create a new PRD for a web-based application where users drop in files, the system uploads them, detects the file workflow/template and case ID, gets user approval, then packs parts, generates supports for die/tooth cases, and sends jobs to the printer queue automatically.

## Desired Outcome

An execution-ready requirements artifact that defines the product intent, scope, non-goals, decision boundaries, constraints, and testable acceptance criteria for a web-based successor or extension of the current FormFlow Dent / Andent workflow.

## Stated Solution

Build a web-based application that:
- accepts dropped files
- uploads them
- detects workflow/template
- derives case ID
- requests user approval
- packs parts
- generates supports for die/tooth
- dispatches automatically to a printer queue

## Probable Intent Hypothesis

The user likely wants to move the current semi-automated desktop dental-prep workflow into a browser-accessible intake and approval product with less manual operator work and a stronger path to automatic preparation and print dispatch.

## Known Facts / Evidence

- The repository is brownfield and already contains dental workflow classification logic in `andent_classification.py`.
- `andent_classification.py` already derives case IDs from filenames via `extract_case_id()` and classifies artifacts/workflows via `classify_artifact()`.
- Existing workflows include `ortho_implant`, `tooth_model`, `splint`, and `manual_review`.
- `api_client.py` already exposes scene auto-support and local printer dispatch flows via `auto_support_scene()` and `send_scene_to_local_printer()`.
- `app_gui.py` already contains queue management, folder intake, local printer selection, and an `Andent V2 auto-dispatch to real printers` setting.
- `Andent/04_customer-facing/mvp-local-test-guide.md` states the current MVP intentionally avoids printer dispatch in Andent mode.
- The same guide also states tooth-model automation is intentionally disabled pending verified support-touchpoint constraints.

## Constraints

- This is a PRD workflow, not implementation.
- The codebase suggests important existing safety gates around ambiguous case IDs, manual review, tooth-model preparation, and printer dispatch.
- The new request implies a web product while the current implementation is primarily desktop-oriented.

## Unknowns / Open Questions

- Whether this is a net-new web product, a web front end on top of current services, or a hybrid with the current desktop pipeline.
- Who the approving user is and what approval UX is required.
- Whether auto-dispatch should happen immediately after approval or only under additional gating.
- Which workflows are truly in scope for automatic packing and support generation.
- Whether case ID detection must be fully automatic or operator-correctable.
- Whether the system should support multi-case uploads, mixed workflows, and ambiguous files.
- What counts as success from the business/operator perspective.

## Decision-Boundary Unknowns

- What the product may auto-decide without operator confirmation.
- Which failure modes must hard-stop to manual review.
- Whether template/workflow detection may be low-confidence or probabilistic.
- Whether printer selection is automatic, rule-based, or operator-selected.

## Likely Codebase Touchpoints

- `andent_classification.py`
- `andent_planning.py`
- `processing_controller.py`
- `api_client.py`
- `app_gui.py`
- `local_printer_controller.py`
- `Andent/04_customer-facing/*.md`
