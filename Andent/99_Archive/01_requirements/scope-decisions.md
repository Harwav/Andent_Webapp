# Deep Interview Spec: Andent MVP PRD

## Metadata
- Profile: standard
- Rounds: 4
- Final ambiguity: 0.18
- Threshold: 0.20
- Context type: brownfield
- Interview session: `019d7247-b873-78d0-9f31-5edc6399b539`
- Context snapshot: `.omx/context/andent-mvp-prd-20260409T124736Z.md`
- Transcript: `.omx/interviews/andent-mvp-prd-20260409T130231Z.md`

## Clarity Breakdown
| Dimension | Score |
| --- | --- |
| Intent | 0.82 |
| Outcome | 0.82 |
| Scope | 0.86 |
| Constraints | 0.82 |
| Success | 0.66 |
| Context | 0.84 |

## Intent
Extend the existing FormFlow Dent platform into an Andent-specific MVP that automates the preparation of dental print builds for Formlabs workflows with minimal operator effort, while keeping production safety high through workflow-specific rules and a mandatory approval gate before printing.

## Desired Outcome
An operator can feed a folder of Andent STL exports into FormFlow Dent, have the system automatically classify files, group them by case, apply workflow-specific preparation rules, prepare a printable build artifact plus screenshot, and stop for approval. The operator should not need to manually rebuild scenes in PreForm for normal in-scope cases.

## In Scope
- Build on existing FormFlow Dent infrastructure, not a separate forked product.
- Add an Andent MVP workflow layer that distinguishes at least:
  - ortho / implant models
  - tooth models
  - splints / bite guards
- Classify file types using:
  - filename patterns first
  - STL geometry heuristics as a secondary signal
- Use case identity as a hard grouping unit for build planning.
- Allow multiple cases on one build only when each case remains fully contained on that build.
- For ortho / implant models:
  - use Precision Model Resin
  - use `50 micron` layer height
  - print flat on the build platform
  - use no supports
  - auto hollow through the Formlabs local API path already aligned with current FormFlow Dent capabilities
- For tooth models:
  - identify them from naming plus geometry
  - auto-generate supports
  - constrain touchpoints to the lower approximately `7-8 mm`
  - avoid touchpoints above that region to protect critical surfaces
- For splints / bite guards:
  - leverage Formlabs Dental Workspace behavior or nearest available local API equivalent
  - prepare them through the same approval-gated build flow
- Generate prepared output artifacts for review:
  - prepared build/file
  - screenshot image for approval
- Stop before any printer dispatch.
- Fail unsafe or unresolvable cases into manual review.

## Out Of Scope / Non-goals
- No automatic printer dispatch in the MVP.
- No forced autonomous completion for tooth-model cases when the bottom-only support rule cannot be satisfied safely.
- No in-app manual support editing, sculpting, or CAD tools.
- No Formlabs cloud, Fleet, or dashboard workflows in MVP.
- No support for additional dental artifact types unless they fit the defined workflow rules without expanding scope.
- No post-print production tracking, patient management, or external business-system integrations.

## Decision Boundaries
- FormFlow Dent may automatically:
  - classify artifacts using filename and geometry heuristics
  - group related files by case
  - batch multiple cases onto one build if each case remains intact on that build
  - apply workflow-specific build-prep rules
  - prepare a build artifact and screenshot for approval
- FormFlow Dent may not automatically:
  - send approved builds to printers in the MVP
  - split one case across multiple builds
  - continue unsafe tooth-model preparation once the support-region rule cannot be preserved with confidence

## Constraints
- Same-case artifacts must stay on the same build.
- If a case cannot fit on one build under the chosen workflow and safety rules, that case must fail to manual review.
- Tooth-model supports must stay constrained to the lower approximately `7-8 mm` region.
- The system should minimize human intervention, but production safety and tooth-surface protection override full autonomy.
- MVP should remain local-first through PreFormServer / Formlabs Local API.
- Capability claims should distinguish:
  - verified local API support
  - inferred but unverified feasibility

## Testable Acceptance Criteria
- The system can ingest Andent sample folders and classify files into the target workflow families with explainable rules.
- The system can derive a case grouping key robust enough to keep all files from the same case together.
- The system never splits one case across multiple builds.
- The system can batch multiple cases together only when full case cohesion is preserved.
- If a case does not fit on a single build, the system flags it for manual review rather than splitting it.
- Ortho / implant model jobs can be prepared with the defined flat, no-support, `50 micron`, Precision Model workflow.
- Tooth-model jobs attempt automated support generation only under the constrained lower-region rule.
- If the lower-region support rule cannot be achieved with confidence, the job is flagged for manual review.
- Splint / bite-guard jobs can be prepared through a workflow aligned with Dental Workspace behavior where supported by the local API.
- Every successful prepared build emits:
  - a build artifact
  - a screenshot for approval
- No build is automatically dispatched to a printer in the MVP path.

## Assumptions Exposed And Resolutions
- Assumption: current FormFlow Dent is already close to the ortho / implant workflow.
  - Resolution: accepted as likely true based on user statement and brownfield code context.
- Assumption: tooth-model automation is still desired despite higher safety risk.
  - Resolution: confirmed; automation remains in scope, but with a strict support-region rule and manual-review fallback.
- Assumption: throughput matters, but case integrity matters more than absolute packing density.
  - Resolution: confirmed; case cohesion is a hard rule and overflow cases must fail to review.
- Assumption: full printer automation is not required for MVP value.
  - Resolution: confirmed; prepared-build approval is the chosen boundary.

## Pressure-Pass Findings
- Revisiting the “same case must stay on the same build” rule revealed a real tradeoff with build-capacity optimization.
- Final rule hierarchy:
  - case cohesion beats packing efficiency
  - safety beats autonomy
  - approval gate beats auto-dispatch

## Brownfield Evidence Vs Inference Notes
- Verified from repository:
  - FormFlow Dent already contains scene creation, scene save, batch `scan-to-model`, processing orchestration, and local printer coordination.
  - Relevant files include `api_client.py`, `processing_controller.py`, `local_printer_controller.py`, and `app_gui.py`.
- Verified from sample set:
  - customer dataset includes `218` STL files in `sample_STL/` and `24` splint STLs in `Splints/`
  - filename families include unsectioned models, tooth artifacts, antagonists, model bases, model dies, and bite splints
- Verified from Formlabs documentation available locally and online:
  - exact Local API `0.9.13` HTML endpoint is reachable
  - bundled `0.9.11` schema in the repo documents `scan-to-model`, `hollow`, `auto-support`, `auto-layout`, `save-screenshot`, `print`, and `DENTAL` mode
- Inference:
  - Dental Workspace-like splint preparation is likely partially available through the Local API path, but field-level workflow parity still needs direct implementation validation
  - there is no verified explicit API control yet for “touchpoints only below 7-8 mm”; that likely requires either heuristic scene logic, indirect parameterization, or a conservative fail-to-review gate

## Technical Context Findings
- Existing architecture already supports local scene-based preparation via Formlabs APIs.
- Existing roadmap/workflow planning in `Andent/PLAN_workflow-preset-variant.md` supports a first-class workflow/preset abstraction inside the same application.
- The MVP should likely be implemented as:
  - workflow classification layer
  - case-group-aware batching planner
  - workflow-specific processing policy resolver
  - approval artifact generator

## Handoff Recommendation
Recommended next step: `$ralplan`

Rationale:
- Requirements are now sufficiently clarified.
- The main remaining work is architecture and feasibility planning around:
  - workflow policy structure
  - case grouping and batching algorithm
  - tooth-model support-safety strategy
  - approval artifact UX and persistence

## Condensed Transcript
- R1: tooth models should still be automated, but with touchpoints constrained to the bottom `7-8 mm`; same-case files stay on one build
- R2: system stops at prepared build/file plus screenshot for approval
- R3: accepted MVP non-goals around no auto-dispatch, no cloud, no manual CAD, no extra scope
- R4: if a case cannot fit on a single build, fail to manual review instead of splitting
