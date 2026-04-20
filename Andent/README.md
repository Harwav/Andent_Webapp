# Andent Project Dossier

## Purpose
This folder is the active working dossier for the current Andent web-app track on top of FormFlow Dent.

The main `Andent/` tree is intentionally kept minimal so the current project is easy to follow.
Older MVP and V2 discussion/planning material has been moved into `99_Archive/`.

## Current Structure

### `00_context/`
- current web-auto-prep context snapshot
- current interview record
- sample data summary that still informs the active track

### `01_requirements/`
- current source-of-truth requirement document for the web-auto-prep effort

### `02_planning/` — [📁 View](02_planning/)
| # | Document | Purpose |
|---|----------|---------|
| 00 | `00_README.md` / `00_AGENTS.md` | Documentation index & agent navigation |
| 01 | `01_PRD-andent-web.md` | Product Requirements Document |
| 02 | `02_Architecture-andent-web.md` | System architecture & design |
| 03 | `03_Algorithm-classification.md` | Classification algorithm specification |
| 04 | `04_Roadmap-implementation.md` | Implementation timeline |
| 05 | `05_TestSpec-andent-web.md` | Test specifications |
| 06 | `06_Future/` | V2+ planned improvements |
| 98 | `98_VerificationArtifacts/` | Test logs & verification data |

### `03_validation/`
- reserved for current-track validation notes

### `04_customer-facing/`
- reserved for current-track customer-safe documents

### `99_Archive/`
- superseded MVP, V2, and earlier planning/discussion material

## Current Canonical Docs

### Requirements
- [01_requirements/prd-andent-web.md](01_requirements/prd-andent-web.md)

### Planning
- [02_planning/01_PRD-andent-web.md](02_planning/01_PRD-andent-web.md) — Product Requirements
- [02_planning/02_Architecture-andent-web.md](02_planning/02_Architecture-andent-web.md) — System Architecture
- [02_planning/03_Algorithm-classification.md](02_planning/03_Algorithm-classification.md) — Classification Algorithm
- [02_planning/04_Roadmap-implementation.md](02_planning/04_Roadmap-implementation.md) — Implementation Roadmap
- [02_planning/05_TestSpec-andent-web.md](02_planning/05_TestSpec-andent-web.md) — Test Specifications

### Context
- [00_context/context-andent-web-auto-prep-20260415.md](00_context/context-andent-web-auto-prep-20260415.md)
- [00_context/interview-andent-web-auto-prep-20260415.md](00_context/interview-andent-web-auto-prep-20260415.md)

## Working Rules
- Keep only current-track material in `00_context/`, `01_requirements/`, `02_planning/`, `03_validation/`, and `04_customer-facing/`.
- Move superseded discussions, plans, validation notes, and customer drafts into `99_Archive/`.
- Keep `.omx/` for runtime/orchestration artifacts only.
