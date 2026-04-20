# Customer Brief

## Customer
Andent

## Project Goal
Build an MVP on top of FormFlow Dent that can automatically prepare Formlabs-ready dental builds with minimal operator effort, while stopping at an approval gate before printing.

## Core Workflow Scope
- Ortho / implant models
- Tooth models
- Splints / bite guards

## Key Business Rules
- All files from the same case must stay on the same build.
- A single case may not be split across multiple builds.
- Multiple cases may share one build.
- If a case cannot fit on one build under workflow constraints, it fails to manual review.
- Successful builds stop at prepared artifact plus screenshot for approval.
- MVP does not auto-dispatch to printers.

## Source Material
- Customer sample folder:
  - `/Users/marcus.liang/Desktop/BM/20260409_Andent_Matt`
- Customer-facing discussion draft:
  - [../04_customer-facing/customer-approval-plan.md](/Users/marcus.liang/Documents/FormFlow_Dent/Andent/04_customer-facing/customer-approval-plan.md)
