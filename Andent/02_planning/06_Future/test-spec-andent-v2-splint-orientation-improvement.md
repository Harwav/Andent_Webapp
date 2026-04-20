# Test Spec: Andent V2 Splint Orientation Improvement

> **Context:** This improvement is planned for the Andent Web pipeline. It was originally scoped against the desktop app but will be implemented as part of the web product.

## Metadata
- Created: 2026-04-11T00:00:00Z
- Source plan: `Andent/02_planning/prd-andent-v2-splint-orientation-improvement.md`
- Source PRD baseline: `Andent/02_planning/prd-andent-v2-unattended-dispatch.md`

## Test Strategy
Prove that the Andent V2 splint path now enforces the intended scene outcome, not just the nominal API call sequence.

## Scope Under Test
- Splint policy resolution
- Splint material/layer scene payload selection
- Splint orientation/support/layout sequencing
- Splint outcome verification before export
- Splint failure routing when the required orientation result is not achieved

## Test Categories

### 1. Unit Tests: Splint Policy
- Splint policy resolves to:
  - `LT Clear V2`
  - `0.100 mm`
  - `15 deg`
  - supports required
  - support touchpoint guard required
- Splint policy strips hollow-only scan params when hollowing is disabled.

### 2. Unit Tests: Required Scene Payload Resolution
- The selected printer family resolves a scene payload compatible with `LT Clear V2` and `0.100 mm`.
- Missing `LT Clear V2` profile routes to manual review / non-export path.

### 3. Integration Tests: Splint Scene Sequencing
- Splint processing order is:
  - auto-orient
  - auto-layout
  - auto-support
  - auto-layout
- Scene verification runs after the final relayout, not only before supports.

### 4. Integration Tests: Outcome Verification
- A sufficiently tilted splint with supports passes and exports.
- A splint that remains effectively flat after orientation/layout fails the export gate.
- A splint that loses supports after relayout fails the export gate.
- Multi-model splint scenes require every model to satisfy the splint outcome checks.

### 5. Integration Tests: Artifact Gate
- Passing splint scenes save:
  - `.form`
  - sibling screenshot
- Failing splint scenes do not export `.form` or screenshot artifacts.

### 6. Manual Validation Matrix
- Single splint case:
  - preview shows tooth profile facing up
  - preview shows a clear tilted posture
  - support generation is present
  - material/layer settings are correct
- Multi-splint build:
  - every splint remains tilted after relayout
  - supports remain present
  - validation passes before export

## Fixtures And Mocks
- Splint STL fixtures
- Mocked scene metadata for:
  - correctly tilted splint
  - too-flat splint
  - support loss after relayout
  - multi-model splint scene with one bad model
- Mocked preset data including:
  - valid `LT Clear V2` profile
  - missing-profile case

## Exit Criteria
- Splint policy tests pass.
- Splint sequencing and outcome-verification tests pass.
- Passing splint scenes export artifacts.
- Failing splint scenes do not export artifacts.
- Manual validation confirms previews match the intended splint orientation rule.

## Known Risks To Track During Execution
- Preview-based manual validation is still the final reality check for "tooth profile facing up."
- API metadata may not expose a perfect geometric proof of the intaglio direction, so the verification stack must combine multiple signals.
