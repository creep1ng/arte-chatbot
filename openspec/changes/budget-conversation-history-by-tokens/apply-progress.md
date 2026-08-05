# Apply Progress: Complete Token-Budgeted Conversation History
## Delivery and cumulative completion
Strategy `stacked-to-main`. PR #292 exact preflight and PR #298 replay are merged;
`main@da46cbf` is the v3 base and preserves the replay CLI. Evidence v3 commit
`71960a5` adds only 9 test + 312 report lines. Defaults v3 starts at `71960a5` and
ports README/env/all OpenSpec, with a ≤330-line pre-verify budget. PR #299 remains
open and separate for latency/routing. Unrelated package locks remain modified and
unstaged with preserved bytes. Tasks 0.1–4.3 are complete; fresh verify is pending.

## TDD Cycle Evidence
| Task | RED | GREEN | REFACTOR |
|---|---|---|---|
| 1.1–1.4 | Missing exact preflight required boundary/parity/no-create/safe-log coverage. | Merged #292 counts before create and fails closed. | Shared local mappings plus full count/create parity assertions; create-only output/cache. |
| Review fixes | Create/preflight traceback leaked provider sentinel. | Safe failures and cleanup tests passed. | Parameterized regression; metric/type-only logs. |
| 2.1–2.3 | Missing deterministic replay. | Merged #298 provides pinned offline generation and tests. | Fixture hash, fail-closed corpus, canonical serializer, retained CLI. |
| 3.1–3.3 | Main lacked committed results/equality test. | `71960a5` regenerates the canonical bytes. | Evidence diff is exactly 321 lines and excludes replay code. |
| 4.1–4.3 | Main lacked rationale/env/change record. | Defaults/docs v3 covers six defaults and caveats. | Canonical statuses, bases, risks, budgets, and verify placeholder updated. |

## Reconstruction evidence
- Evidence replay CLI and focused suite passed; generated SHA-256 is
  `788520a9213ab58db79f434abdd8a9ed0320d2ba3ba38863c160fe6c3aca5b2d`.
- Final context is 1,368 input/20 turns; cumulative use is 14,497 input + 510 output
  = 15,007. Replay tests: 6 passed; strict OpenSpec: valid; scoped Ruff format/check
  and mypy: clean for both replay Python files; diff checks: clean. Defaults/docs are
  285 additions including the 10-line placeholder, below the 330-line pre-verify cap;
  replacing it with a report of up to 70 lines keeps the final slice at ≤345.

## Guards, deviations, risks
Lock SHA-256 preserved: `.kilo` `2e94ea3555aada9636815f34c0f7d35c5ba1fb9b9952fd1c50b4dd51a4ac6b47`;
`.kilocode` `5e55b1d2e2569c58e75a6fb887683c877a837ed7249fd97ccac7707df572f979`.
No design deviation: canonical code shares mapped values and proves count/create
parity without a frozen request-shape type. File Input outages fail closed and may
reduce availability. Replay accepts only the hashed corpus and needs audited counts/
new fixture hash after edits. It does not validate production PDF extraction or
reasoning; defaults remain preliminary pending telemetry. Status: implementation
tasks complete; ready for a fresh verify phase.
