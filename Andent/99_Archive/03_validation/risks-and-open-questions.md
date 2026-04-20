# Risks And Open Questions

## Primary Risks
- Tooth-model support behavior may not be controllable with enough precision through available Formlabs Local API parameters.
- Splint workflow parity with Dental Workspace may differ from what is exposed through PreFormServer.
- Current processing flow is still centered on global `api_params`, which is a weak fit for workflow-specific policies.
- Existing aligner behavior could regress if workflow branching is introduced without regression coverage.

## Open Questions
- Can the lower `7-8 mm` tooth support rule be represented directly, or does it need geometry-aware prechecks plus fail-to-review logic?
- What should the approval screenshot contain to be operationally useful:
  - full build plate only
  - multiple angles
  - build metadata overlay
- Should approval mode always export `.form`, or also emit a sidecar summary file?

## Validation Priorities
- Prove screenshot export end to end.
- Prove case-aware planning with no case splitting.
- Prove oversized single-case failure behavior.
- Prove tooth-model safety fallback behavior.
