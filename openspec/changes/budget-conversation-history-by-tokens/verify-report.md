# Verification Report — Final

**Change:** `budget-conversation-history-by-tokens`

**Range:** `main@da46cbf` → `71960a5` → `b2618ba`

**Mode:** standard SDD verify; **Verdict:** PASS WITH WARNINGS; **Gate:** GO

## Completeness

| Check | Result |
|---|---|
| Issue #262 acceptance criteria | 13/13 PASS |
| Delta-spec scenarios | 12/12 PASS with runtime coverage |
| Tasks | 15/15 complete; no unchecked task |
| Design | Coherent; shared count/create mappings replace the rejected duplicate-shape approach |
| Replay/evidence | CLI retained; two offline runs and committed report are byte-identical |

## Acceptance criteria

| # | Evidence | Status |
|---:|---|---|
| 1 | Immutable registry/version pins and capability tests | PASS |
| 2 | Ratio, hard cap, output and non-history reserves are configurable | PASS |
| 3 | Selector admits only complete turns | PASS |
| 4 | Newest fitting suffix returns chronologically | PASS |
| 5 | System/tools/current input/output/File Input accounting is conservative | PASS |
| 6 | Unknown model/tokenizer and unprovable File Input safety fail closed | PASS |
| 7 | Decision/failure/cleanup logs omit content, paths, IDs, PII and exception bodies | PASS |
| 8 | Short/oversized/Unicode/sources/unknown/exact-boundary tests pass | PASS |
| 9 | `max_turns` remains a secondary ceiling | PASS |
| 10 | Offline fixture contains 20 Spanish 10–30-word exchanges | PASS |
| 11 | Every turn records input/output/total and cumulative metrics | PASS |
| 12 | Final context (1,368) differs from cumulative total (15,007) | PASS |
| 13 | Six defaults have evidence rationale, preliminary labels and telemetry caveats | PASS |

## Scenario matrix

| Scenario | Passing runtime evidence | Status |
|---|---|---|
| Known model budget | config/model/file-budget focused tests | PASS |
| Unknown capability | unknown-model/tokenizer and no-create tests | PASS |
| Short/oversized histories | selector focused tests | PASS |
| Exact/Unicode/sources | selector boundary/preservation tests | PASS |
| Turn ceiling | `test_max_turns_is_a_secondary_ceiling` | PASS |
| Exact File Input boundary | count-before-create exact/one-over tests | PASS |
| Unprovable File Input safety | failed/missing counter and unknown-model tests | PASS |
| Count/create equivalence | full mapped-kwargs parity test | PASS |
| Safe success/failure logs | history, byte/token, preflight and cleanup tests | PASS |
| Replay identical | replay test plus two CLI `cmp` runs | PASS |
| Context vs consumption | report metric assertions | PASS |
| Defaults rationale | executable README/env assertion (6/6) | PASS |

## Execution evidence

- Offline suite: `pytest -m "not live"` — 717 passed, 4 deselected.
- Focused budget/replay suites — 119 passed; replay suite alone included 6 passed.
- Replay CLI ran twice; both matched `results.json`, SHA-256 `788520a9…ca5b2d`.
- Strict OpenSpec: valid. Replay files: Ruff check/format and scoped mypy: clean.
- PR #299 head `c927fba`: 38 focused tests pass; Ruff/format pass; routing=`low`,
  File Input reasoning=`none`, output cap=512, incomplete/create failures fail closed.
- PR #299 CI run `31029598184` and preview smoke job `92387827536`: SUCCESS.
- `git diff --check`, ancestry and locks pass. Slices: PR #299 174, evidence 321,
  final docs/OpenSpec including this report <400 changed lines.

## Warnings

- PR #299 remains open and separate from this v3 documentation chain; merge status is
  an integration-order concern, not a missing issue criterion in the verified range.
- Full offline tests emit one third-party Mangum event-loop deprecation warning.
- Exploratory mypy over PR #299's whole client dependency graph reports existing
  untyped boto3/OpenAI SDK overload issues; requested scoped replay mypy is clean.
