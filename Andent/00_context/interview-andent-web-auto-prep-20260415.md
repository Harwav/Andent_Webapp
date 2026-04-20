## Deep Interview Transcript Summary

- Profile: `standard`
- Context type: `brownfield`
- Final ambiguity: `14.7%`
- Threshold: `20%`
- Context snapshot: `Andent/00_context/context-andent-web-auto-prep-20260415.md`

## Brownfield grounding

- `andent_classification.py` already contains workflow classification and case ID extraction logic.
- `api_client.py` already contains auto-support and printer dispatch methods.
- `app_gui.py` already contains queue and printer selection concepts.
- `Andent/04_customer-facing/mvp-local-test-guide.md` documents current safety limits: no printer dispatch in Andent mode and no tooth-model automation.
- The interview established that those current limits are not requirements for the new PRD; they are to be removed for standard cases.

## Condensed transcript

### Round 1

- Target: `Intent Clarity`
- Question: What is the main business outcome this web app must optimize for?
- Answer: `eliminate manual preparation of print jobs`

### Round 2

- Target: `Scope Clarity`
- Question: Which steps must become fully automatic?
- Answer: `workflow/template detection, case ID confirmation, orientation/packing, support generation, and sending to printer group. Outliers can be escalated for human review and approval, but should not be more than 2% of the cases`

### Round 3

- Target: `Decision Boundaries`
- Question: What counts as an outlier that must stop automation?
- Answer: `low-confidence workflow/template match, ambiguous or missing case ID`

### Round 4

- Target: `Constraints` (pressure pass)
- Question: Should the current tooth auto-prep and printer auto-dispatch safeguards remain?
- Answer: `Yes remove them`

### Round 5

- Target: `Non-goals`
- Question: What should phase 1 explicitly not cover?
- Answer: `manual support tweaking tools, printer-fleet optimization`

### Round 6

- Target: `Success Criteria`
- Question: What launch metric proves manual prep has been replaced successfully?
- Answer: `>=95% straight-through processing`

## Pressure-pass finding

- Revisited prior brownfield assumptions around safety gates.
- Outcome: current MVP restrictions on tooth auto-prep and printer auto-dispatch were explicitly rejected as phase-1 product constraints.
