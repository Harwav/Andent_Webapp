# Workflow Preset Variant Plan

## Summary

Build this as one product, not a separate fork: add a first-class workflow/preset layer to the existing app so users can choose `Aligner`, `Splint`, or `Orthotic` from a prominent top-level selector. The active workflow applies to the whole current queue, is remembered between launches, and drives both defaults and workflow-specific rules, while printer/material/layer-height/FPS remain separate job-level choices.

## Key Changes

- Add a workflow preset domain model with:
  - protected built-ins: `aligner`, `splint`, `orthotic`
  - user-created custom presets derived from built-ins
  - persisted `current_workflow_id`
  - persisted preset library with `id`, `name`, `base_workflow_id`, `is_builtin`, `api_params`, and workflow rule flags
- Migrate current app behavior into the built-in `Aligner` preset.
  - Existing `api_params` become the initial Aligner baseline.
  - Initial `Splint` and `Orthotic` built-ins start as copies of the current defaults and are tuned later.
- Add a top-level workflow selector in the main UI, above or beside the existing print settings area.
  - Selecting a workflow updates the quick settings/sidebar and readiness state immediately.
  - Add preset actions: duplicate, rename custom preset, delete custom preset, reset built-in.
- Keep printer/material/layer-height/FPS outside the workflow preset model.
  - Workflow presets control FormFlow behavior and API parameter defaults only.
  - Existing "Use Custom Preset" (`.fps`) flow remains, but workflow selection still governs app-side rules and sidebar defaults.
- Introduce a workflow rules layer between UI state and `ProcessingController`.
  - Rules can alter visible/relevant settings, readiness checks, smart batching heuristics, and validation messaging.
  - Do not add new processing primitives in v1.
  - Do not add workflow-specific support generation in v1.
- Refactor persistence so settings are no longer centered on one global mutable `api_params` object.
  - Keep backward compatibility by migrating old installs into `current_workflow_id=aligner` plus a preserved current preset state.
  - Continue storing queue-level app settings and output/general preferences separately.
- Adjust processing behavior to resolve a `selected_workflow_preset` before job start.
  - `ProcessingController` should consume a resolved workflow config object, not read ad hoc workflow assumptions from scattered settings.
  - Aligner-specific heuristics and comments become explicitly workflow-scoped rather than global app assumptions.

## Public Interfaces / Types

- Extend persisted settings schema with:
  - `current_workflow_id`
  - `workflow_presets`
  - `workflow_preset_version`
- Add an internal resolved type/interface for execution, e.g. `ResolvedWorkflowPreset`, containing:
  - preset identity and metadata
  - resolved `api_params`
  - workflow rule flags for batching, validation, and UI capability toggles
- Add a small preset management surface in the UI:
  - workflow selector
  - preset duplicate/reset/delete actions
  - built-in vs custom preset distinction

## Test Plan

- Migration tests:
  - existing users without workflow data load into `Aligner` without losing current behavior
  - old settings files upgrade cleanly and remain saveable
- Preset persistence tests:
  - switching workflows updates active values correctly
  - duplicating a built-in creates an editable custom preset
  - editing a custom preset does not mutate the built-in seed
  - resetting a built-in restores shipped defaults
- Queue/rules tests:
  - one active workflow applies to the full queue
  - changing workflow updates readiness logic and visible defaults before processing
  - printer/material/FPS selections remain independent from workflow presets
- Processing tests:
  - existing Aligner flow remains behaviorally unchanged
  - workflow-specific batching/rule resolution reaches `ProcessingController` deterministically
  - no support-generation behavior is introduced accidentally
- UI tests:
  - top-level selector persists last-used workflow
  - preset actions are disabled/enabled correctly for built-in vs custom presets

## Assumptions And Defaults

- Ship one app with workflows, not a separate branded fork.
- v1 built-ins are `Aligner`, `Splint`, and `Orthotic`.
- Workflows affect defaults and rules, not printer/material/FPS ownership.
- One workflow applies to the whole active queue.
- Built-ins are protected; users customize via duplicate-to-edit.
- v1 includes workflow-aware defaults, validation/readiness rules, and batching heuristics only.
- v1 does not add new printer operations such as support generation.
- Initial `Splint` and `Orthotic` seed values start as copies of current defaults and are tuned afterward.
