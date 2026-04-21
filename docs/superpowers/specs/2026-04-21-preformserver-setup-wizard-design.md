# PreFormServer Setup Wizard Design

Date: 2026-04-21
Status: Approved design
Scope: First-run setup, managed install, version gating, and maintenance flow for local PreFormServer on Windows

## Summary

This design adds a managed `PreFormServer Setup Wizard` to Andent Web.

The wizard is a real product feature, not only a test prerequisite. It guides the user through local ZIP-based installation, managed replacement with newer ZIPs, service start and restart, health verification, and version compatibility checks for the local PreFormServer dependency.

The wizard is also a hard print gate. Print-dependent features must remain blocked until the managed PreFormServer install is present, compatible, and healthy.

The first version supports local ZIP install and local ZIP replacement only. It does not download installers from the network.

## Problem

Andent Web now depends on a live local PreFormServer instance for real print handoff, but the current product experience assumes that dependency is already installed, already running, and already compatible.

That leads to the wrong user experience:

1. First-run users hit raw connection failures instead of a guided setup flow.
2. Version mismatch and upgrade handling are implicit rather than explicit.
3. Release-gate verification depends on machine state that the app does not help manage.
4. Supportability suffers when the app has no single managed install path or maintenance surface.

The system needs one clear answer to the question, "Is this machine ready for print handoff?"

## Goals

1. Provide a first-run wizard that guides users to install and start PreFormServer from a local ZIP.
2. Keep one canonical managed PreFormServer install owned by Andent Web.
3. Block print-dependent features until PreFormServer readiness is confirmed.
4. Detect and explain distinct readiness failures such as missing install, stopped service, incompatible version, invalid ZIP, or failed health check.
5. Reuse the same surface later for repair, restart, and ZIP-based update.
6. Preserve a clean path for future release-gate automation: `wizard -> ready -> print handoff`.

## Non-Goals

1. Download PreFormServer from a remote source in v1.
2. Search the whole machine for arbitrary unmanaged PreFormServer copies and adopt them automatically.
3. Replace PreFormServer's own print logic, queueing, or layout behavior.
4. Add cross-platform installer support in the first version; this design is scoped to Windows.
5. Hide every low-level detail from the user. The wizard should be guided, but still explicit about failures.

## Core Principle

Andent Web should manage and verify one canonical local PreFormServer install.

That means:

1. One expected install location.
2. One expected launch command.
3. One explicit version-compatibility contract.
4. One readiness state machine shared by first-run setup, ongoing maintenance, and print gating.

The product should not rely on "whatever PreFormServer happens to be installed somewhere on this machine" in the first version.

## Readiness Lifecycle

The app should expose a `PreFormServer readiness` state with four main states:

1. `not_installed`
   No managed install exists in the expected location.
2. `installed_not_running`
   A managed install exists, but the local API is not reachable.
3. `incompatible_version`
   A managed install exists, but the detected version is outside the accepted contract.
4. `ready`
   The managed install exists, the version is accepted, and the local API passes health checks.

Additional transient sub-states may exist internally for UX and orchestration:

1. `installing`
2. `replacing`
3. `starting`
4. `checking_health`
5. `failed`

These transient states support progress UI, but the persistent user-facing readiness contract should stay simple.

## Product Gating

PreFormServer readiness should be a hard gate for print-dependent actions.

If readiness is not `ready`:

1. `Send to Print` must be disabled or intercepted.
2. Any print handoff attempt must redirect the user into the setup flow instead of surfacing a raw connection error.
3. Print Queue surfaces may remain visible, but must clearly show setup state instead of pretending live queue operations are available.

If readiness is `ready`:

1. Print actions are enabled.
2. Queue polling and handoff use the managed PreFormServer configuration.

This preserves intake and review workflows while preventing avoidable handoff failures.

## User Experience Model

The first-run wizard should be the first face of a persistent `PreFormServer Setup Center`.

That means the same underlying system supports:

1. first-run install
2. update required flow
3. restart and repair
4. re-check health
5. replace with newer ZIP

### First Run

On first run, if readiness is anything other than `ready`, the user should land in a full-screen setup wizard before using print-dependent functionality.

The wizard should explain:

1. why PreFormServer is required
2. what Andent Web will manage locally
3. what ZIP the user needs to select
4. what success looks like

### Ongoing Maintenance

After setup, the same capabilities should remain available from a persistent maintenance surface such as Settings or an equivalent operations panel.

The app should also show a degraded-state banner or card when readiness falls out of `ready`.

## Install Location

The first version should use one app-managed Windows install location:

`%APPDATA%/Andent Web/PreFormServer/`

This location is recommended because it:

1. matches the local-user, local-app ownership model
2. avoids ambiguity about which copy Andent Web is launching
3. makes replace and repair flows predictable
4. aligns with the historical Formflow Dent direction captured in the repository notes

## ZIP-Based Install Flow

The first version supports local ZIP selection only.

Example source:

`D:\Marcus\Downloads\PreFormServer_3.57.2.624.zip`

### Install Steps

1. Detect current readiness state.
2. Ask the user to choose a local ZIP file.
3. Validate the ZIP before extraction.
4. Extract to a staging directory, not directly into the managed install path.
5. Verify the staged contents contain the expected executable layout.
6. Replace the managed install atomically from staging.
7. Launch the managed `PreFormServer.exe` on the configured port.
8. Poll health until success or timeout.
9. Read and validate the reported version.
10. Mark readiness as `ready` and unlock print features.

### ZIP Validation Rules

Before install or replace, the app should verify:

1. the selected file exists
2. the extension is `.zip`
3. file size exceeds a minimum sanity threshold
4. the archive contains the expected `PreFormServer.exe` payload layout

If validation fails, the wizard must explain whether the failure is:

1. wrong file type
2. corrupt archive
3. missing executable layout
4. unsupported package shape

## Update Flow

Updates should reuse the same ZIP-driven mechanism as install.

If the installed version is incompatible:

1. readiness becomes `incompatible_version`
2. print-dependent actions remain blocked
3. the setup center shows `Update Required`
4. the user selects a newer local ZIP
5. the app stages, replaces, restarts, and re-verifies

The first version should support replacement with a newer ZIP, but not direct online download.

## Service Control

The backend should own managed process control for the canonical install.

Supported actions:

1. `start`
2. `stop`
3. `restart`
4. `recheck`

The launch path should be explicit and stable:

`%APPDATA%/Andent Web/PreFormServer/PreFormServer.exe --port 44388`

If port binding fails or startup times out, the readiness state should move to a failure state with a clear explanation.

## Version Compatibility

The app should enforce a version-compatibility contract instead of relying on best effort.

The first version should use a pinned supported version or a tightly bounded accepted range defined in one place. The wizard then compares the detected PreFormServer version against that contract during:

1. startup
2. install completion
3. manual re-check

If the version is incompatible:

1. readiness becomes `incompatible_version`
2. handoff remains blocked
3. the setup center prompts for replacement with a newer ZIP

## Architecture

The design should stay narrow and service-oriented.

### 1. `preformserver_manager`

A backend service should own:

1. managed install-path resolution
2. ZIP validation
3. staged extraction
4. atomic replace
5. process launch and stop
6. health polling
7. version detection
8. readiness-state evaluation

### 2. Setup State Persistence

A small persistence surface should track:

1. managed install path
2. detected version
3. last successful health check
4. last known readiness state
5. last setup or startup error
6. whether the managed install is the active configured source

The persistence model should be simple enough to survive app restarts and support user-visible status.

### 3. API Surface

The backend should expose dedicated setup routes for:

1. `GET status`
2. `POST install-from-zip`
3. `POST start`
4. `POST stop`
5. `POST restart`
6. `POST recheck`
7. `POST replace-from-zip`

### 4. Frontend Surface

The frontend should contain:

1. a full-screen first-run wizard
2. a persistent maintenance panel
3. degraded-state banners or cards when readiness is not `ready`

## Error Model

The wizard must distinguish between different failure shapes. At minimum:

1. `missing_install`
2. `bad_zip`
3. `install_failed`
4. `start_failed`
5. `port_unavailable`
6. `health_check_failed`
7. `incompatible_version`

The UI should never collapse those into a single generic "PreFormServer error" message when the system already knows the precise problem.

## Relationship To Release Gate

This wizard is not the same feature as the Playwright release gate, but they should reinforce each other.

The setup wizard improves the product dependency story for real users. The release gate then proves the browser-to-app-to-PreForm handoff on a prepared local machine.

Longer term, the browser test story can cover:

1. wizard gating before readiness
2. setup success from a local ZIP
3. transition into `ready`
4. print handoff after readiness

## Testing Strategy

Testing should be split into three layers.

### Unit Tests

Required proof points:

1. install-path resolution
2. ZIP validation
3. staged extraction and replace logic
4. version parsing
5. compatibility checks
6. readiness-state derivation

### Backend Integration Tests

Required proof points:

1. install-from-zip route behavior
2. persisted readiness state
3. startup and restart flows
4. blocked print behavior when readiness is not `ready`
5. successful transition from `not_installed` or `incompatible_version` to `ready`

### Browser Tests

Required proof points:

1. first-run wizard appears when readiness is not `ready`
2. print actions are blocked before setup
3. local ZIP install flow completes successfully
4. incompatible version state prompts for replacement
5. print actions unlock only after readiness becomes `ready`

## Risks And Mitigations

### Risk: Installer ambiguity

If the app supports arbitrary unmanaged PreFormServer copies in v1, compatibility and supportability become unclear.

Mitigation:

1. Use one canonical managed install path.
2. Make the wizard own that copy explicitly.

### Risk: Half-installed state

If extraction writes directly into the live install path, interrupted installs may leave the product unusable.

Mitigation:

1. Always extract to staging.
2. Replace atomically after validation.

### Risk: Confusing print failures

If readiness is known but the UI still exposes live print actions, users will keep hitting raw connection errors.

Mitigation:

1. Enforce a hard print gate.
2. Redirect setup-related failures into the wizard rather than surfacing transport errors first.

### Risk: Scope creep into generic updater infrastructure

If v1 tries to support remote downloads, generic package management, or unmanaged install adoption, delivery risk rises quickly.

Mitigation:

1. Keep v1 local-ZIP only.
2. Keep version management explicit and narrow.

## Acceptance For This Design

This design is complete when implementation planning can answer:

1. where readiness state is persisted
2. how ZIP validation identifies a supported PreFormServer package
3. how staging and atomic replace are implemented on Windows
4. how process lifecycle is managed safely by the backend
5. how the frontend routes first-run users into the wizard
6. how print actions are gated when readiness is not `ready`
7. which version contract the app enforces in the first release
8. which unit, integration, and browser tests lock the setup and gating behavior

Those are implementation-plan questions, not unresolved design questions.
