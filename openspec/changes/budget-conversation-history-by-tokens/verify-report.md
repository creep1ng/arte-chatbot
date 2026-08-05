# Final Verification Report

**Change:** `budget-conversation-history-by-tokens`
**Range:** canonical `main@21ef771..d43e511` plus this report
**Mode:** fresh-context standard verification; OpenSpec strict
**Verdict:** **PASS WITH WARNINGS — GO**

## Gate summary

| Gate | Result |
|---|---|
| Tasks | 15/15 checked and evidenced |
| Specification | 12/12 scenarios compliant |
| Issue #262 | 13/13 acceptance criteria compliant |
| Delivery | `ab2e3f7` 173; `e41abe8` 399; `8642b3f` 321; docs/report slice <400 changed lines |
| Scope | No committed lockfile; only this report changed by verification |

## Execution evidence

| Check | Fresh result |
|---|---|
| Full offline suite: `uv run pytest -m "not live"` | 723 passed; 4 live deselected |
| Focused budget/config/routing/file/chat/replay suite | 177 passed; 3 skipped |
| Replay suite twice | 7 passed + 7 passed |
| Two in-process regenerations versus committed bytes | identical; 9,117 bytes; SHA-256 `788520a9...ca5b2d` |
| `openspec validate budget-conversation-history-by-tokens --strict` | valid |
| Scoped Ruff check + format | passed; 12 files formatted |
| Isolated policy/replay mypy | passed; 6 source files |
| Changed-file mypy including `llm_client.py` | non-clean; warning below |
| Diff/slice/lock checks | passed after report update |
| Coverage | not configured or collected |

## Issue #262 acceptance criteria

| # | Criterion | Runtime/source evidence | Status |
|---:|---|---|---|
| 1 | Versioned model registry | capability/config tests | PASS |
| 2 | Ratio, hard cap, output and non-history reserves | config and budget tests | PASS |
| 3 | Newest complete turns | selector tests | PASS |
| 4 | Chronological result | selector tests | PASS |
| 5 | Conservative system/tools/message/output/file accounting | accounting and exact preflight tests | PASS |
| 6 | Unknown model/tokenizer fails closed | zero-history/no-count/no-create tests | PASS |
| 7 | Content/PII-safe decision logs | sentinel success/failure tests | PASS |
| 8 | Short/oversized/Unicode/sources/unknown/boundaries | focused runtime suite | PASS |
| 9 | Secondary `max_turns` ceiling | ceiling test | PASS |
| 10 | Reproducible 20-exchange Spanish simulation | fixture and cold offline test | PASS |
| 11 | Per-turn and accumulated input/output/total | report contract test | PASS |
| 12 | Final context differs from cumulative consumption | 1,368 vs 14,497 + 510 = 15,007 | PASS |
| 13 | Preliminary evidence-based defaults | README/env contract inspection and replay evidence | PASS |

## Spec scenario compliance

| Requirement / scenario | Passing evidence | Status |
|---|---|---|
| Policy / known model budget | model, config, budget tests | COMPLIANT |
| Policy / unknown capability | history and File Input rejection tests | COMPLIANT |
| History / short and oversized | contiguous selector tests | COMPLIANT |
| History / boundary, Unicode, sources | selector and replay boundary tests | COMPLIANT |
| History / turn ceiling | `max_turns` tests | COMPLIANT |
| Accounting / exact File Input boundary | exact/one-over and no-create tests | COMPLIANT |
| Accounting / unprovable safety | unknown/unavailable/failed/invalid tests | COMPLIANT |
| Accounting / count-create equivalence | ordered events and complete shared-key assertion | COMPLIANT |
| Observability / safe success and failure | sentinel logs, no traceback/chaining | COMPLIANT |
| Replay / identical regeneration | two suites plus canonical byte comparison | COMPLIANT |
| Replay / context versus consumption | metric invariants | COMPLIANT |
| Defaults / evidence and caveats | six defaults plus PDF/reasoning/telemetry caveats | COMPLIANT |

## Latency regression and live evidence

- `ab2e3f7` keeps ordinary tool routing functional at reasoning `medium`; File Input
  uses reasoning `none` and `max_output_tokens=512`.
- Exact count occurs before create; excess, unavailable, failed, malformed, unknown,
  and `incomplete` responses fail closed. Uploaded-file cleanup remains in `finally`;
  failure logs omit content, paths, file/session IDs, exception bodies, and traceback.
- PR #299 run `31027312239`, job `92380010124`, completed successfully at head
  `ab2e3f7`: health/chat passed, `source_documents=1`, persistence passed, and the
  same-endpoint harness completed 5/5 (average 7,817.93 ms; max 14,024.73 ms).
  This proves live routing/File Input/source return, but the logs do not print the
  response body, so they do **not** independently prove the requested 605 W answer.

## Findings and final gate

**CRITICAL:** None.

**WARNING:** Full changed-file mypy reports seven findings: five transitive missing
boto stubs and OpenAI SDK overload mismatches at both the ordinary and File Input
`responses.create` calls. Isolated policy/replay typing passes; CI does not gate mypy.

**WARNING:** Design names a frozen `FileInputRequestShape`; implementation instead
reuses the same local mappings for count/create and proves parity at runtime. Behavior
matches the spec, but immutability is not structurally enforced.

**WARNING:** README repeats “production”; the live smoke log cannot attest response
text correctness. Two unrelated package locks remain modified but uncommitted.

**GO.** Behavioral, fail-closed, latency, routing, cleanup, log-safety,
reproducibility, strict OpenSpec, diff, lock, and slice-budget gates pass.

**skill_resolution:** `sdd-verify` executed directly as the verify executor;
`cognitive-doc-design` applied to keep evidence review-first and compact.
