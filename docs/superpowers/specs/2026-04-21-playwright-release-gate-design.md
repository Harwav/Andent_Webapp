# Playwright Release Gate Design

Date: 2026-04-21
Status: Drafted and reviewed for implementation planning
Scope: Release-blocking end-to-end acceptance gate for Andent Web

## Summary

This design defines a Playwright-driven release gate for Andent Web that simulates operator behavior in the browser while using a live PreFormServer instance on `http://localhost:44388` for handoff verification.

The gate is intentionally narrow. It is not a broad acceptance suite and it does not prove Formlabs cloud or printer completion. It proves that the current release candidate can:

1. Accept realistic STL inputs that follow production-style naming conventions.
2. Classify and present them correctly in the web UI.
3. Allow a standard happy path and a manual-correction happy path to reach real PreFormServer handoff.
4. Block an ambiguous case from being sent.
5. Surface a clean failure when the app is configured against an unavailable PreFormServer endpoint.

## Problem

The repository now has strong automated pytest coverage for service and API behavior, but release confidence still depends on one missing proof surface: an operator-level browser journey against the real local PreFormServer handoff boundary.

The release gate must close that gap without becoming a slow, fragile, full-platform validation suite.

## Goals

1. Block release if the browser flow is broken for the current intake-to-handoff boundary.
2. Use Playwright to simulate human interaction through the existing UI.
3. Verify real handoff to a live local PreFormServer instance on `localhost:44388`.
4. Verify one same-case multi-file straight-through path.
5. Verify one manual-edit path where the operator changes `Model Type` and explicitly overrides `Preset`.
6. Verify one ambiguous-case guard that remains blocked in `Active`.
7. Verify one offline failure path against a separate app instance configured to a dead local PreFormServer port.
8. Produce operator-readable pass/fail output with artifacts suitable for release decisions.

## Non-Goals

1. Prove Formlabs cloud synchronization or printer completion.
2. Replace the existing pytest suite.
3. Cover every queue behavior, duplicate behavior, or batching edge case.
4. Exercise destructive service operations such as killing and restarting the live PreFormServer during the test run.
5. Depend on broad, unstable sample fixtures that were not chosen specifically for release gating.

## Release Gate Scope

The release gate consists of exactly four scenarios:

1. Straight-through happy path.
2. Manual-edit happy path.
3. Ambiguous-case guard.
4. Offline failure path.

Anything beyond those four scenarios is out of scope for the first gate and should remain in normal pytest or later acceptance expansion.

## Scenario Contract

### 1. Straight-Through Happy Path

Input:
- A realistic same-case multi-file STL set.
- File names must follow production-style naming patterns, including case IDs and classification cues.

Expected browser behavior:
- The rows appear in the web UI.
- The case reaches a sendable state without manual edits.
- The operator can send the case to print.
- The UI reflects successful submission.

Expected non-UI verification:
- The app records the resulting handoff identifiers such as `scene_id` and `print_job_id`.
- The gate performs a direct check against the live PreFormServer API to confirm that the created scene or print job exists.

### 2. Manual-Edit Happy Path

Input:
- A realistic STL input set named in the same style as real inbound lab files.
- The fixture must still be suitable for operator recovery rather than being irrecoverably blocked.

Expected browser behavior:
- The operator changes `Model Type`.
- The UI applies its normal synchronization behavior.
- The operator then explicitly overrides `Preset`.
- The case becomes sendable and is submitted successfully.

Expected non-UI verification:
- The app records resulting handoff identifiers.
- The gate performs a direct check against the live PreFormServer API to confirm the scene or print job exists after the edited submission.

### 3. Ambiguous-Case Guard

Input:
- A realistic but intentionally ambiguous STL input whose naming convention fails case-ID certainty or otherwise yields a blocked review-style state.

Expected browser behavior:
- The row remains blocked in `Active`.
- `Send to Print` is unavailable for that case.

Expected non-UI verification:
- No extra backend verification is required beyond confirming that a send path is not exposed by the UI for this first release gate.

### 4. Offline Failure Path

Input:
- A realistic sendable STL input.
- A second app instance configured to a dead local PreFormServer port.

Expected browser behavior:
- The operator can reach the normal send step.
- The send attempt surfaces a visible failure.
- The row must not transition into a false success state.

Expected non-UI verification:
- The gate records the app instance URL and the dead-port configuration used for the failure path so the failure is attributable and reproducible.

## Architecture

The release gate uses three layers.

### Layer 1: Release-Gate Runner

The runner owns environment startup, teardown, and scenario orchestration.

Responsibilities:
1. Start a normal app instance for live-service scenarios.
2. Start a second app instance configured to a dead local PreFormServer port for the offline scenario.
3. Perform a direct health check against `http://localhost:44388` before live scenarios begin.
4. Fail fast if live PreFormServer health is not available.
5. Expose the app base URLs and runtime metadata to the browser tests.

This keeps startup and health logic out of UI steps.

### Layer 2: Playwright Acceptance Tests

The Playwright layer owns operator simulation only.

Responsibilities:
1. Open the app in the browser.
2. Upload fixture files.
3. Wait for classification and visible final states.
4. Perform manual edits where required.
5. Click `Send to Print`.
6. Verify visible browser outcomes.

The browser tests should read like operator workflows, not backend diagnostics.

### Layer 3: Verification Helpers

Verification helpers own non-UI assertions.

Responsibilities:
1. Read app-side persisted identifiers needed to prove handoff.
2. Query the live PreFormServer API directly for created scenes or print jobs.
3. Confirm that negative scenarios did not result in false success evidence.

This separation preserves readable UI tests while still making the gate strict enough for release blocking.

## Fixture Strategy

The release gate should use a very small dedicated fixture set, not a broad reuse of mixed repo samples.

Rationale:
1. Release blockers need deterministic inputs.
2. The fixtures must prove filename-driven classification behavior.
3. The fixtures should be stable over time and easy to reason about when failures occur.

Fixture rules:
1. All STL names must follow realistic inbound naming conventions, including case IDs and workflow cues where appropriate.
2. The straight-through fixture must be a same-case multi-file upload.
3. The manual-edit fixture must still look realistic while being appropriate for operator correction.
4. The ambiguous fixture must look plausible as a real inbound file set while intentionally yielding a blocked state.

The first implementation should keep the fixture set minimal:
1. One same-case multi-file happy-path set.
2. One manual-edit set.
3. One ambiguous set.

The offline failure path can reuse a sendable fixture from the happy-path or manual-edit set.

## Runtime Model

The gate owns startup for the web app instances.

Responsibilities of the gate:
1. Start app instance A with the normal live PreFormServer URL.
2. Start app instance B with a dead local PreFormServer URL for the offline scenario.
3. Verify PreFormServer health before scenario execution.
4. Shut down both app instances after the run.

The gate does not own starting or stopping the live PreFormServer process itself. It assumes the service is already available locally and checks health before beginning.

This is the safest split between automation and environmental stability:
1. It keeps the app runtime deterministic.
2. It avoids flaky kill-and-restart behavior for the local print service.
3. It still proves the real network failure path through the dead-port app instance.

## Verification Contract

### Happy Paths

A happy-path scenario passes only if all of the following are true:

1. The browser flow completes successfully.
2. The UI reflects successful submission.
3. The app records the handoff identifiers.
4. A direct query to the live PreFormServer API confirms the created scene or print job exists.

UI-only success is insufficient.

### Ambiguous Guard

The ambiguous-case scenario passes only if:

1. The case remains blocked in `Active`.
2. `Send to Print` is not available.

### Offline Failure

The offline failure scenario passes only if:

1. The browser reaches the send action.
2. The app surfaces a visible failure.
3. No false success state is shown.

## Pass/Fail Reporting

The release gate must emit compact, decision-ready output.

For each scenario, it should record:
1. Scenario name.
2. App base URL used.
3. Whether live PreFormServer health was confirmed before the run.
4. Final browser-visible result.
5. Any app-side handoff identifiers observed.
6. Direct PreFormServer verification result when required.

On failure:
1. Capture a Playwright screenshot.
2. Record the failing assertion.
3. Record enough context to distinguish UI failure, app failure, and external verification failure.

This output should be suitable for a release decision without requiring someone to reconstruct the failure from raw logs alone.

## Recommended File Layout

The implementation should keep the release gate isolated from the main pytest suite's existing structure.

Recommended shape:

```text
tests/
  release_gate/
    fixtures/
    test_release_gate.spec.ts
    helpers/
    artifacts/
```

The exact final layout may adapt to the repo's existing conventions during planning, but the release-gate code should remain clearly isolated from the current Python-only test surfaces.

## Risks And Mitigations

### Risk: Fixture instability

If release fixtures are borrowed opportunistically from older validation assets, classification behavior may drift or become unclear.

Mitigation:
- Keep the fixture set intentionally small and dedicated.
- Use realistic names with explicit expected behavior.

### Risk: PreFormServer environmental flakiness

Live local service availability can fail for reasons unrelated to the app.

Mitigation:
- Fail fast on health check before live scenarios.
- Keep the offline scenario on a dead-port app instance rather than manipulating the live service.

### Risk: Browser tests becoming too broad

If more product coverage is added immediately, the suite may become slow and brittle.

Mitigation:
- Lock the first gate to the four approved scenarios only.

## Acceptance For This Design

This design is complete when implementation planning can answer:

1. Which exact realistic STL fixtures will be used.
2. How the app instances will be started and torn down.
3. How app-side persisted handoff identifiers will be read for verification.
4. Which direct PreFormServer endpoints will be queried to confirm scene or print existence.
5. Where screenshots and scenario summaries will be written.

Those are implementation-plan questions, not open design questions.
