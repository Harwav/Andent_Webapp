# Andent Web Pre-Release Verdict - 2026-04-28

## Candidate
- Commit: 446e4e1d2249bb52ac26a3c1e723f53e2578a530
- Branch: main
- Operator: Marcus
- Machine: MARCUS-LAPTOP
- PreFormServer version: Not proven; `/api/preform-setup/status` timed out during evidence capture.
- Primary dataset: `D:\Marcus\Desktop\BM\20260409_Andent_Matt\Test Data`
- App settings summary: default uvicorn app on `127.0.0.1:8090`; Playwright isolated app on `127.0.0.1:8200` with `test-results/playwright-app-data`.

## Gate Results
| Gate | Result | Evidence |
|------|--------|----------|
| Backend pytest suite | PASS | pytest.log: 262 passed, 5 warnings |
| TypeScript compile | FAIL | tsc.log: TS2835 import-extension errors and implicit-any errors in release_gate tests |
| Browser smoke/UI checks | FAIL | playwright-smoke.log: 2 failed, 2 passed |
| Headed browser observation | FAIL | playwright-headed.log: 2 failed, 2 passed |
| Live PreForm browser handoff | FAIL | playwright-live-preform.log: timeout; PreForm wizard overlay intercepted row selection |
| Straight-through rate >=95% | FAIL | validate-launch.log timed out during 242-file upload; launch-check.json timed out |
| Human-review rate <=2% | FAIL | Required current-candidate metric unavailable; launch-check.json timed out |
| Upload p95 latency <=30s | FAIL | Required current-candidate metric unavailable; validation upload exceeded script timeout |
| Dispatch success >=99%, non-vacuous | FAIL | No live PreForm dispatch proof; print-job-evidence.json timed out |
| Review boundaries | FAIL | Required fixture/manual notes not established because browser/validation gates failed |
| Artifact durability | FAIL | Required print job/artifact evidence unavailable |

## Fixture Set
- Dataset inventory: dataset-inventory.md
- Standard ortho: Not proven in current candidate.
- Standard splint: Not proven in current candidate.
- Standard tooth/die: Not proven in current candidate.
- Review guard: Browser UI hook fixture failed to find expected Ready row.
- Duplicate guard: Bulk duplicate Playwright check passed in mocked browser gate, but full release gate failed.
- Mixed compatibility: Not proven in current candidate.
- Held-build/release: Not proven in current candidate.

## Decision
- Verdict: RELEASE BLOCKED
- Blocking failures: TypeScript compile, browser smoke/UI, headed browser observation, live PreForm handoff, launch validation timeout, missing launch metrics, missing non-vacuous dispatch evidence, missing artifact durability proof.
- Non-blocking risks: Backend pytest emitted STL mesh warnings; not release-blocking by itself.
- Follow-up owner: Engineering.
