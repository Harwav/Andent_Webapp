# 02_planning: Planning Module

## OVERVIEW

Technical planning documents for Andent Web — requirements, architecture, algorithms, roadmap, and test specifications.

## STRUCTURE

```
02_planning/
├── 00_README.md                          # Documentation index for humans
├── 00_AGENTS.md                          # This file — navigation guide for agents
├── 01_PRD-andent-web.md                  # Product Requirements Document (Phase 0+)
├── 02_Architecture-andent-web.md         # System architecture and component design
├── 02.01_Algorithm-classification.md     # Classification algorithm specification
├── 02.02_Architecture-PreFormServer-handoff.md # PreFormServer handoff design
├── 04_Roadmap-implementation.md          # Phased implementation plan
├── 05_TestSpec-andent-web.md             # Test specifications and acceptance criteria
├── 06_Future/                            # V2+ future improvements
│   ├── plan-andent-v2-build-quality-improvements.md
│   ├── prd-andent-v2-splint-orientation-improvement.md
│   ├── test-spec-andent-v2-splint-orientation-improvement.md
│   └── flowchart-andent-v2-unattended-dispatch.mmd
└── 98_VerificationArtifacts/              # Live verification test artifacts
    ├── live_splint_verification_*
    └── verification_test_data_*/
```

## DOCUMENT HIERARCHY

```
01_PRD-*.md (What — requirements)
    ↓ (constrains)
02_Architecture-*.md (How high-level — design)
    ↓ (designs)
03_Algorithm-*.md (How detailed — implementation)
    ↓ (implements as)
Code (core/, app/)
    ↓ (verified by)
05_TestSpec-*.md (How we verify)
    ↓ (tracked in)
04_Roadmap-*.md (When — timeline)
```

## WHERE TO LOOK

| Question | Document | Section |
|----------|----------|---------|
| What model types exist? | `01_PRD-andent-web.md` | "In Scope" → Phase-1 Model Type values |
| What are the accuracy targets? | `01_PRD-andent-web.md` | "Testable Acceptance Criteria" |
| How does the system architecture work? | `02_Architecture-andent-web.md` | Section 2 "Architecture Diagram" |
| What are the classification thresholds? | `02.01_Algorithm-classification.md` | Section 3.3.2 "Structure Detection Thresholds" |
| How does the system decide solid vs hollow? | `02.01_Algorithm-classification.md` | Section 3.3 "Structure Resolution" |
| Which keywords trigger which model type? | `02.01_Algorithm-classification.md` | Section 3.2 "Artifact Classification" |
| What confidence levels exist? | `02.01_Algorithm-classification.md` | Section 3.5 "Confidence Derivation" |
| When does a case need human review? | `01_PRD-andent-web.md` | "Decision Boundaries" |
| What are the test coverage requirements? | `05_TestSpec-andent-web.md` | "Classification And Decision Boundaries" |
| What's the current implementation phase? | `04_Roadmap-implementation.md` | "Progress Summary" |
| What V2 improvements are planned? | `06_Future/prd-andent-v2-splint-orientation-improvement.md` | Full document |

## FILE NAMING CONVENTION

**Pattern**: `##_Type-descriptive-name.md`

| Prefix | Type | Content |
|--------|------|---------|
| `00_` | Navigation | README, AGENTS |
| `01_` | PRD | Requirements, acceptance criteria |
| `02_` | Architecture | System design, API contracts |
| `03_` | Algorithm | Implementation details, thresholds |
| `04_` | Roadmap | Timeline, phases, progress |
| `05_` | TestSpec | Test coverage, validation |
| `06_` | Future/V2 | Planned improvements |
| `98_` | Artifacts/Data | Logs, verification data |
| `99_` | Archive | Superseded documents |

## CONVENTIONS

- **PRD (`01_PRD-*.md`)**: Requirements — what the system must do
- **Architecture (`02_Architecture-*.md`)**: How the system works — components, data flow, API
- **Algorithm (`03_Algorithm-*.md`)**: Implementation details — thresholds, formulas, code refs
- **Roadmap (`04_Roadmap-*.md`)**: When we build — phased delivery plan
- **Test Spec (`05_TestSpec-*.md`)**: How we verify — test cases, coverage

## ANTI-PATTERNS

- **No code in planning docs**: Algorithms reference code, don't duplicate it
- **No implementation details in PRD**: PRD says *what*, algorithm doc says *how*
- **No thresholds without code references**: Every threshold must cite `file.py:line`
- **No orphaned docs**: Every doc must be linked from 00_README.md

## CROSS-REFERENCE FORMAT

**Code references**: Use `` `file.py:line` `` format
```markdown
| HOLLOW_MAX_FILL_RATIO | 0.28 | `core/andent_classification.py:35` |
```

**Doc references**: Use relative paths with anchors
```markdown
See [Section 3.3](02.01_Algorithm-classification.md#33-structure-resolution)
```

## UNIQUE STYLES

- **Threshold tables**: All numeric thresholds must include code location (file:line)
- **Version annotations**: Major changes should have "Added YYYY-MM-DD" notes
- **Decision logs**: When changing thresholds, document the rationale

## NOTES

- Planning docs are **living documents** — update when code changes
- Keep PRD stable; put evolving details in algorithm docs
- When in doubt: PRD = intent, Architecture = design, Algorithm = implementation

## REFERENCES

- Requirements: `../01_requirements/prd-andent-web.md`
- Context: `../00_context/`
- Validation: `../03_validation/`
- Customer-facing: `../04_customer-facing/`
- Archive: `../99_Archive/`
