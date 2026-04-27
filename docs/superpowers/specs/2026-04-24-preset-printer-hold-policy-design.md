# Preset, Printer Group, And Holding Policy Design

> Date: 2026-04-24
> Status: Implemented and verified 2026-04-27

## Purpose

Lock the Phase 1 contract for Andent Web presets, Form 4B/Form 4BL support, PreFormServer scene settings, and build holding behavior before implementation.

## Preset Contract

Andent keeps exactly 7 UI presets:

| UI preset | Stable PreForm hint | Material label | Layer | Default printer | Also valid |
|-----------|---------------------|----------------|-------|-----------------|------------|
| Ortho Solid - Flat, No Supports | `ortho_solid_v1` | `Precision Model V1` | 100 um | Form 4BL | Form 4B |
| Ortho Hollow - Flat, No Supports | `ortho_hollow_v1` | `Precision Model V1` | 100 um | Form 4BL | Form 4B |
| Die - Flat, No Supports | `die_v1` | `Precision Model V1` | 100 um | Form 4BL | Form 4B |
| Tooth - With Supports | `tooth_v1` | `Precision Model V1` | 100 um | Form 4BL | Form 4B |
| Splint - Flat, No Supports | `splint_v1` | `LT Clear V2` | 100 um | Form 4BL | Form 4B |
| Antagonist Solid - Flat, No Supports | `antagonist_solid_v1` | `Precision Model V1` | 100 um | Form 4BL | Form 4B |
| Antagonist Hollow - Flat, No Supports | `antagonist_hollow_v1` | `Precision Model V1` | 100 um | Form 4BL | Form 4B |

The `*_v1` hint strings are stable API contract values. Future incompatible changes use new hint versions.

Material labels are the compatibility source of truth because they are human-readable. Material codes remain API-boundary details:

- `Precision Model V1` -> `FLPMBE01`
- `LT Clear V2` -> `FLDLCL02`

## Behavior Rules

The six flat/no-support presets keep imported orientation, lay flat on the platform, allow auto-layout, and forbid generated supports.

Hollow presets mean the STL is already hollowed. Phase 1 does not hollow or otherwise alter them.

`Tooth - With Supports` assumes imported files are already bottom-down. It may generate supports only for tooth models, and support contact must stay on the bottom/support-safe side. If this cannot be verified or satisfied, the tooth case routes to review.

Tooth may share builds with other `Precision Model V1` presets when printer group and layer match. Splint may share only with other Splint cases because it uses `LT Clear V2`. Same-case Splint plus non-Splint rows route to review in Phase 1. Same-case mixed printer-group targets also route to review.

## Scene Settings

Scene settings come from the manifest compatibility group, not server defaults.

| Printer group | Material label | `machine_type` | `material_code` | `layer_thickness_mm` | `print_setting` |
|---------------|----------------|----------------|-----------------|----------------------|-----------------|
| Form 4BL | Precision Model V1 | `FRML-4-0` | `FLPMBE01` | `0.1` | `DEFAULT` |
| Form 4B | Precision Model V1 | `FORM-4-0` | `FLPMBE01` | `0.1` | `DEFAULT` |
| Form 4BL | LT Clear V2 | `FRML-4-0` | `FLDLCL02` | `0.1` | `DEFAULT` |
| Form 4B | LT Clear V2 | `FORM-4-0` | `FLDLCL02` | `0.1` | `DEFAULT` |

Auto-layout uses `model_spacing_mm = 1` for all printers and presets, with `allow_overlapping_supports = false`.

## Packing Contract

Form 4BL uses the existing `69,188 mm^2` platform budget. Form 4B uses the existing `25,000 mm^2` platform budget.

The full-arch effective footprint factor `0.58` applies to Form 4BL and Form 4B. This intentionally avoids adding a second tuning variable before Form 4B-specific calibration evidence exists.

Planner budgets stay unchanged despite the new 1 mm layout-spacing target. Future tuning should prefer benchmark-backed changes to the full-arch factor rather than adding a separate budget multiplier.

## Dispatch And Validation

Andent dispatches to a printer group target (`Form 4B` or `Form 4BL`), not to a specific physical printer. Boundary code maps the stable app group target to the configured real PreFormServer printer group/device target.

PreFormServer validation warnings do not block dispatch. Import, scene creation, and layout failures still block because there is no printable scene. Validation results are persisted and shown.

## Holding Policy

Holding uses planner estimated density:

```text
estimated_density = sum(effective_xy_footprint) / printer_xy_budget
```

Defaults:

- single global density target: `40%`
- single global local cutoff: `18:00`

Only the final below-target build per compatibility group can be held. At cutoff, held builds dispatch anyway. After cutoff, new below-target builds dispatch immediately.

The operator must still click **Send to Print** from Active. The system must not silently pull unsent Active rows into a held build. Once rows are sent, they leave Active, enter In Progress, and may appear as **Holding for More Cases** while waiting for compatible future sent rows or cutoff release.

Held builds persist across restart. If a held build is already past cutoff after startup, it waits for operator action instead of dispatching automatically. Operators can manually **Release now** before target or cutoff.

Replanning held builds with newly sent compatible rows must respect the normal planner budget. If replanning produces an above-target build and a new below-target final remainder, the above-target build dispatches and only the final remainder stays held.

## Persisted Metadata

Persist and display:

- compatibility key
- printer group
- material label
- layer height
- row IDs and case IDs
- manifest JSON
- estimated density
- density target
- cutoff time/date used
- hold reason
- release reason
- `released_by_operator`
- `validation_passed`
- `validation_errors`
- timestamps

## Open Risks

Form 4B is not yet density-calibrated. It initially shares the Form 4BL full-arch factor by decision.

The new `model_spacing_mm = 1` target differs from the zero-spacing calibration run. Dense builds may require future factor tuning after live evidence.

Bottom-safe tooth support behavior depends on PreFormServer support capabilities. If it cannot be verified, tooth cases must route to review.
