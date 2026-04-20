# Andent MVP PRD

## Document Info
| Field | Value |
| --- | --- |
| Product | FormFlow Dent for Andent |
| Document | MVP PRD |
| Status | Draft |
| Last Updated | 2026-04-09 |
| Source | Deep interview + sample dataset review |

## Executive Summary
This MVP extends the existing FormFlow Dent product for Andent's production workflow. The goal is to automatically prepare Formlabs-ready dental build files with minimal human intervention, while preserving a strict approval gate before printing.

The MVP focuses on three workflow families:
- ortho / implant models
- tooth models
- splints / bite guards

The product should automatically classify incoming STL files, keep all files from the same case on the same build, prepare workflow-specific print scenes, export a prepared build artifact, generate a screenshot, and stop for operator approval.

## Problem Statement
Andent's current workflow still depends on manual judgment and manual build preparation in cases where STL exports vary by artifact type and naming quality. This creates avoidable labor, inconsistency, and bottlenecks, especially when operators must rebuild scenes in PreForm for common cases.

The main automation challenge is not simple file import. It is safe workflow-specific preparation:
- ortho / implant models need a flat, support-free workflow
- tooth models require controlled support behavior that does not touch critical tooth surfaces
- splints should leverage dental-specific preparation behavior where available
- same-case files must stay together on one build

## Product Goal
Reduce operator work from full manual build preparation to approval-only review for normal Andent cases.

## Success Outcome
For an in-scope Andent input folder, FormFlow Dent should:
1. classify files by artifact/workflow type
2. group files by case
3. plan builds while preserving case cohesion
4. apply workflow-specific preparation rules
5. generate a prepared build artifact and screenshot
6. stop for approval before any print dispatch

## Users
- Primary user: dental lab technician preparing daily Formlabs builds
- Secondary user: production lead reviewing prepared builds before release

## Scope

### 1. Case And Artifact Classification
The system must classify STL files using filename patterns first and STL geometry heuristics second.

Target artifact families in MVP:
- unsectioned jaw models
- tooth models
- model bases / dies where relevant to case preparation
- splints / bite guards

### 2. Case-Cohesive Build Planning
All files from the same case must remain on the same build.

Rules:
- one case cannot be split across multiple builds
- multiple cases may share one build
- if a case cannot fit on one build under workflow and safety rules, the system must fail that case for manual review

### 3. Ortho / Implant Workflow
For ortho / implant models, the system should prepare builds using:
- Precision Model Resin
- `50 micron` layer height
- flat-on-platform orientation
- no supports
- automatic hollowing through the Formlabs local API workflow already aligned with current FormFlow Dent infrastructure

### 4. Tooth Model Workflow
For tooth models, the system should:
- detect likely tooth-model artifacts using filename and geometry
- auto-generate supports
- constrain support touchpoints to the lower approximately `7-8 mm`
- avoid touchpoints above that region to protect critical surfaces

If the system cannot preserve that lower-region support rule with sufficient confidence, it must fail the case to manual review rather than continue automatically.

### 5. Splint / Bite Guard Workflow
For splints and bite guards, the system should leverage Formlabs Dental Workspace behavior or the nearest supported equivalent exposed by the Formlabs Local API / PreFormServer workflow.

### 6. Approval Output
Each successfully prepared build must output:
- a prepared build file or equivalent prepared artifact
- a screenshot for operator approval

The MVP stops at approval. It does not auto-send the build to the printer.

## Non-goals
- automatic printer dispatch
- in-app manual support editing or CAD operations
- cloud/Fleet/dashboard workflows
- post-print production tracking
- patient-management workflows
- broader dental artifact support beyond the agreed workflow families unless they fit the same rules without expanding scope

## Functional Requirements

### FR1. Input Handling
- ingest STL files from Andent input folders
- classify files into workflow-relevant artifact groups
- derive a stable case identifier from naming conventions and related heuristics

### FR2. Build Grouping
- keep all files from one case on the same build
- permit multi-case builds only when each case remains intact
- fail overflow cases into manual review

### FR3. Workflow Policy Resolution
- apply workflow-specific preparation rules based on classified artifact family
- surface why a case was assigned to a given workflow

### FR4. Automated Preparation
- create the required scene and processing sequence
- apply hollowing / support / layout behavior according to workflow
- preserve a conservative fallback for ambiguous or unsafe cases

### FR5. Approval Package
- export the prepared build artifact
- generate a screenshot of the prepared scene
- present the build as awaiting approval

## Acceptance Criteria
- A normal in-scope Andent folder can be processed into classified cases and prepared builds without manual rebuilding in PreForm.
- Same-case artifacts are never split across builds.
- A case that cannot fit on one build is flagged for manual review.
- Ortho / implant jobs use the expected `50 micron`, flat, no-support workflow.
- Tooth-model jobs are only auto-prepared when supports can be kept within the lower region.
- Successful builds include screenshot-based approval evidence.
- No automatic print dispatch occurs in the MVP path.

## Risks
- The Formlabs Local API clearly exposes generic support automation, but direct API control for “touchpoints only below 7-8 mm” is not yet verified.
- Splint workflow parity with Dental Workspace may require implementation validation against the exact local API behavior.
- Geometry-based classification must be conservative enough to avoid unsafe false positives.

## Open Technical Questions
- What is the most reliable implementation approach for the lower-region tooth support rule?
- How should the app display confidence and failure reasons for manual-review cases?
- What artifact format should be the default approval output: `.form`, screenshot only, or both `.form` and exported settings sidecar?

## Recommended Next Step
Run consensus planning on this brief to turn it into implementation architecture and test-spec artifacts.
