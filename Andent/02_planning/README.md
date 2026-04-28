# Andent Web: Planning Documentation

Technical planning documents for the Andent Web Auto Prep system.

## Folder Structure

```
02_planning/
├── 00_README.md                          # This file — documentation index
├── 00_AGENTS.md                          # Navigation guide for AI agents
├── 01_PRD-andent-web.md                  # Product Requirements Document
├── 02_Architecture-andent-web.md         # System architecture & design
├── 02.01_Algorithm-classification.md     # Classification algorithm spec
├── 02.02_Architecture-PreFormServer-handoff.md # PreFormServer handoff design
├── 04_Roadmap-implementation.md          # Implementation timeline
├── 05_TestSpec-andent-web.md             # Test specifications
├── 06_Future/                            # V2+ future improvements
│   ├── plan-andent-v2-build-quality-improvements.md
│   ├── prd-andent-v2-splint-orientation-improvement.md
│   ├── test-spec-andent-v2-splint-orientation-improvement.md
│   └── flowchart-andent-v2-unattended-dispatch.mmd
└── 98_VerificationArtifacts/             # Test logs & verification data
    ├── live_splint_verification_*/
    └── verification_test_data_*/
```

## Quick Navigation

| I Want To... | Go To | File |
|--------------|-------|------|
| **Understand virtual printer debug mode** | 02.04 - Debug Handoff | [`02.04_Architecture-Virtual-Printer-Debug-Handoff.md`](02.04_Architecture-Virtual-Printer-Debug-Handoff.md) |
| **Understand requirements** | 01 — PRD | [`01_PRD-andent-web.md`](01_PRD-andent-web.md) |
| **Understand system design** | 02 — Architecture | [`02_Architecture-andent-web.md`](02_Architecture-andent-web.md) |
| **Understand classification logic** | 02.01 — Algorithm | [`02.01_Algorithm-classification.md`](02.01_Algorithm-classification.md) |
| **Understand PreFormServer handoff** | 02.02 — Handoff | [`02.02_Architecture-PreFormServer-handoff.md`](02.02_Architecture-PreFormServer-handoff.md) |
| **See implementation timeline** | 04 — Roadmap | [`04_Roadmap-implementation.md`](04_Roadmap-implementation.md) |
| **Understand test coverage** | 05 — Test Spec | [`05_TestSpec-andent-web.md`](05_TestSpec-andent-web.md) |
| **See future improvements** | 06 — Future | [`06_Future/`](06_Future/) |
| **Find verification data** | 98 — Artifacts | [`98_VerificationArtifacts/`](98_VerificationArtifacts/) |

## Document Hierarchy

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

## Document Status

| # | Document | Status | Last Updated | Purpose |
|---|----------|--------|--------------|---------|
| 02.04 | Virtual Printer Debug Handoff | Active | 2026-04-28 | Real PreForm endpoint against virtual printer |
| 00 | README / AGENTS | ✅ Active | 2026-04-21 | Navigation |
| 01 | PRD | ✅ Active | 2026-04-21 | Requirements |
| 02 | Architecture | ✅ Active | 2026-04-21 | System design |
| 02.01 | Algorithm | ✅ Active | 2026-04-21 | Classification spec |
| 02.02 | PreFormServer Handoff | ✅ Active | 2026-04-21 | Build manifest handoff design |
| 04 | Roadmap | ✅ Active | 2026-04-21 | Timeline |
| 05 | Test Spec | ✅ Active | 2026-04-21 | Validation |
| 06 | Future (V2) | 🔮 Planned | — | Splint/build quality improvements |
| 98 | Artifacts | 📊 Data | — | Verification logs & test data |

## Classification Documentation

**Status**: ✅ Fully documented in [`02.01_Algorithm-classification.md`](02.01_Algorithm-classification.md)

| Component | Code Location | Document Section |
|-----------|---------------|------------------|
| Case ID extraction | `core/andent_classification.py:139` | Section 3.1 |
| Artifact classification | `core/andent_classification.py:171` | Section 3.2 |
| Structure resolution | `core/andent_classification.py:456` | Section 3.3 |
| Model type mapping | `app/services/classification.py:70` | Section 3.4 |
| Confidence derivation | `app/services/classification.py:92` | Section 3.5 |
| Status assignment | `app/services/classification.py:108` | Section 3.6 |

## For AI Agents

See **[00_AGENTS.md](00_AGENTS.md)** for:
- Navigation patterns
- Convention guidelines
- Cross-reference formats
- Where to find specific information

## File Naming Convention

**Pattern**: `##_Type-descriptive-name.md`

| Prefix | Type | Examples |
|--------|------|----------|
| `00_` | Navigation/Index | `00_README.md`, `00_AGENTS.md` |
| `01_` | PRD (Requirements) | `01_PRD-andent-web.md` |
| `02_` | Architecture | `02_Architecture-andent-web.md` |
| `02.01_` | Algorithm | `02.01_Algorithm-classification.md` |
| `04_` | Roadmap | `04_Roadmap-implementation.md` |
| `05_` | Test Spec | `05_TestSpec-andent-web.md` |
| `06_` | Future/V2 | `06_Future/` folder |
| `98_` | Artifacts/Data | `98_VerificationArtifacts/` folder |
| `99_` | Archive (at root) | `../99_Archive/` |

## Contributing

When adding new planning documents:

1. **Choose the right type** (see File Naming Convention above)
2. **Use the correct prefix** (01_, 02_, etc.)
3. **Link from this README** — Add to Quick Navigation and Document Status tables
4. **Cross-reference code** — Every threshold needs a code location (e.g., `core/andent_classification.py:35`)
5. **Update AGENTS.md** — If adding new conventions or document types

## References

- [Requirements](../01_requirements/)
- [Context](../00_context/)
- [Validation](../03_validation/)
- [Customer-Facing](../04_customer-facing/)
- [Archive](../99_Archive/)
