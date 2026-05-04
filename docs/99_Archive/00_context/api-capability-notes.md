# Formlabs API Capability Notes

## Primary Reference
- Formlabs Local API HTML:
  - `https://formlabs-dashboard-api-resources.s3.us-east-1.amazonaws.com/formlabs-local-api-v0.9.13.html`

## Repo-Local Reference
- `docs/Formlabs Local API (0.9.11).json`

## Verified Relevant Capabilities
- scene creation
- batch `scan-to-model`
- `hollow`
- `auto-layout`
- `print-validation`
- `.form` export
- screenshot export endpoint exists in the documented API
- `DENTAL` mode is documented for layout behavior

## Current Brownfield Gap
- Current FormFlow Dent client does not yet implement:
  - explicit `auto_support_scene()` wrapper
  - explicit screenshot export wrapper

## Main Technical Risk
- Exact support control for “touchpoints only below roughly 7-8 mm” is not yet verified as a direct Local API feature.
- MVP planning assumes a conservative gate:
  - proceed only when the tooth-support rule can be enforced with enough confidence
  - otherwise fail to manual review
