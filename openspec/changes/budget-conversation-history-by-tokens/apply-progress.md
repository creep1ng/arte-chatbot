# Apply Progress: Complete Token-Budgeted Conversation History
## Delivery and cumulative completion
Strategy `stacked-to-main`, 400 lines/slice. S1 exact preflight: 400 lines; S2 replay:
399 additions; S3 evidence on `f18a02e`: 321 additions (9 test + 312 report); S4
docs/change record on `5bdb246`: target ≤340 before verify. Base includes #288
`84850bf`. Unrelated package locks stay modified/unstaged. Completed: [x] 0.1–0.2
base/guards; [x] 1.1–1.4 preflight/tests/SDK/refactor; [x] 2.1–2.3 offline replay;
[x] 3.1–3.3 committed evidence; [x] 4.1–4.3 README/env/compacted complete record.
Rollback only S4; runtime admission, replay, and evidence remain.

## TDD Cycle Evidence
| Task | RED | GREEN | REFACTOR |
|---|---|---|---|
| 1.1–1.4 | Missing policy/shape failed collection; contracts required adapter/parity/no-create/safe logs. | 43 then 61 focused tests passed; verified OpenAI 2.30 count support; all unsafe paths reject. | Shared immutable mappings/error handler; create-only output/cache; suppress exception body/chaining; held 400 lines. |
| Review fixes | Create/preflight traceback leaked provider sentinel. | Safe failures and cleanup tests passed. | Parameterized regression; metric/type-only logs. |
| 2.1–2.3 | Missing module; then cold process rejected runtime tokenizer and mypy rejected tool mapping. | Pinned corpus generator made 4 then 6 tests pass offline. | Fixture hash, fail-closed unknown text, pure canonical serializer, 399 lines. |
| 3.1–3.3 | Byte contract failed: missing `results.json`. | Canonical 312-line report matched regeneration. | Two 7-test runs, 61 backend tests, mypy/Ruff; 321-line boundary. |
| 4.1–4.3 | Docs contract failed: README missing (and env examples incomplete). | README covers reproducible method/commands/metrics, six defaults/caveats; env values match. | Compacted all six artifacts without dropping traceability; strict/tests/regeneration/quality/budget audited. |

## Verification record
- S0/S1: byte guard 21; budget/client 43; budget/client/file 61; cleanup regression 62;
  backend 558 passed/3 skipped; backend Ruff format/check passed; mocks only.
- S2: replay twice 4, then twice 6; cold fresh empty caches denied sockets/URL/API-key
  reads; mypy/Ruff passed; final context 1,368 input/20 turns, cumulative
  14,497 input + 510 output = 15,007.
- S3: replay twice 7; backend focused 61; mypy/Ruff passed; two regenerations equal
  9,117-byte report, SHA-256 `788520a9213ab58db79f434abdd8a9ed0320d2ba3ba38863c160fe6c3aca5b2d`.
- S4: strict OpenSpec passed; replay twice 7 and backend focused 61 passed; exact
  9,117-byte regeneration, replay-scoped Ruff/mypy and `git diff --check` passed;
  295 added docs/config/OpenSpec lines (225 OpenSpec + 58 README + 12 env), below 330/340.

## Guards, deviations, risks
Lock SHA-256 preserved: `.kilo` `2e94ea3555aada9636815f34c0f7d35c5ba1fb9b9952fd1c50b4dd51a4ac6b47`;
`.kilocode` `5e55b1d2e2569c58e75a6fb887683c877a837ed7249fd97ccac7707df572f979`.
No design deviation: one frozen token shape; File Input outages fail closed and may
reduce availability; no content/traceback leakage. Replay reuses registry/selector,
accepts only hashed corpus, and requires audited counts/new fixture hash after edits.
The replay does not validate production PDF extraction/reasoning; defaults remain
preliminary pending production telemetry. Status: 15/15 tasks complete; ready for
verify (verify-report/archive intentionally not created).
