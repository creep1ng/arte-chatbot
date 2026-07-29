# Apply Progress: Preserve PDF Extraction Identity

## Batch

- Mode: Strict TDD
- Delivery: stacked-to-main
- Current unit: Unit 3 publication gate complete after fresh verification corrections
- Scope: cumulative tasks 1.1–3.4
- Verification status: PASS; environmental Ruff warning recorded
- PR gate: final stacked-to-main slice under 400 changed lines; no `size:exception`
- Rollback boundary: each slice reverts independently

## Required PR Separation

Unit 1 is functionally complete and verified, but its 633 code+tests changed lines
exceed the 400-line budget without `size:exception`. Before commit or PR, separate
the existing work into these sequential `stacked-to-main` slices:

1. PR 1A — closed extraction contract: `ClosedDTO`, extraction DTOs,
   `TechnicalParameter`, and recursive/deep-extra tests.
2. PR 1B — trusted identity reconciliation: `TrustedDocument`, opaque IDs,
   exact set reconciliation, and order/anomaly tests. Start from `main` after 1A.
3. PR 1C — review classification and trusted conversion: cardinality, mismatch,
   conversion, and trusted routing. Start from `main` after 1B.

Each slice targets `main` after the preceding slice is integrated, carries its
tests, and has an autonomous rollback boundary. PR 2 starts from `main` after
PR 1C; PR 3 starts from `main` after PR 2.

## Completed Tasks

- [x] 1.1 RED — Closed DTO, expected-ID uniqueness, and exact reconciliation tests.
- [x] 1.2 GREEN — Typed DTOs, trusted records/map, exceptions, and reconciliation.
- [x] 1.3 RED — Trusted routing, cardinality, variants, and mismatch tests.
- [x] 1.4 GREEN — Review classification and trusted-only conversion.
- [x] 1.5 REFACTOR — Consolidated typed helpers with behavior preserved.
- [x] 2.1 RED — Mocked adjacent opaque-ID/File Input request pairs and out-of-order output.
- [x] 2.2 GREEN — Migrated extraction to Files uploads and Responses Structured Outputs.
- [x] 2.3 RED — Covered refusal, incomplete, absent parsed output, parse/API, and cleanup failures.
- [x] 2.4 GREEN — Added source-specific fail-closed response validation without fallbacks.
- [x] 2.5 REFACTOR — Verified OpenAI 1.68.0 supports `responses.parse(text_format=...)`.
- [x] 3.1 RED — Covered review, download, extraction/protocol, conversion, incomplete-batch, and schema failures with zero writes.
- [x] 3.2 GREEN — Added complete-batch accumulation and full-catalog pre-write validation.
- [x] 3.3 RED/GREEN — Adapted local success to Unit 2 publication mappings and trusted routing.
- [x] 3.4 REFACTOR — Removed positional/fallback paths; functional verification passes.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.1 | `scripts/tests/test_generate_index.py` | Unit | 30/30 baseline | ImportError for missing typed boundary; 0 collected | 9/9 identity tests passed in 1.2 | Exact and out-of-order success plus missing, extra/unknown, and duplicate failures | 14/14 Unit 1 tests passed after helper extraction |
| 1.2 | `scripts/tests/test_generate_index.py` | Unit | 30/30 baseline | Tests from 1.1 preceded production code | 9/9 identity tests passed | Closed root/nested DTOs and multiple reconciliation branches | 14/14 Unit 1 tests passed after `_validate_identity_sets()` extraction |
| 1.3 | `scripts/tests/test_generate_index.py` | Unit | 9/9 identity tests | 4 failed and 1 passed before classification/conversion | 5/5 classification/conversion tests passed in 1.4 | Normal variants, zero, multiple, mismatch, and trusted precedence | 14/14 Unit 1 tests passed after typed helper consolidation |
| 1.4 | `scripts/tests/test_generate_index.py` | Unit | 9/9 identity tests | Tests from 1.3 preceded production code | 5/5 classification/conversion tests passed | Cardinality and routing mismatch take distinct paths | 14/14 Unit 1 tests passed after `_review_reasons()`/routing helper cleanup |
| 1.5 | `scripts/tests/test_generate_index.py` | Unit/refactor | 44/44 approval baseline | N/A — behavior-preserving refactor | 14/14 focused tests passed | Existing 14-case Unit 1 matrix preserved | 44/44 final tests passed |
| 2.1 | `scripts/tests/test_generate_index.py` | Unit/SDK request | 51/51 baseline | Initial transport RED plus correction RED (8 failed, 1 passed) preceded fixes | Upload bytes/purpose, no Chat Completions, adjacent opaque pairs, and reversed output pass | Two uploads and partial-upload cleanup covered | 9/9 focused tests passed |
| 2.2 | `scripts/tests/test_generate_index.py` | Unit/transport | 51/51 baseline | Real pipeline probe reproduced tuple caller failure and `Desconocido` fallback | Typed reconciliation converts internally to input-ordered legacy mappings | Reversed model output and realistic caller probe pass | 9/9 focused tests passed |
| 2.3 | `scripts/tests/test_generate_index.py` | Unit/failure policy | Original failure matrix | Central-policy RED: 10 failed, 2 passed; incomplete reason, returned IDs, and external classes leaked | Central `DiagnosticCode` policy emits only application codes and trusted S3 keys | Refusal/incomplete/output/API/upload/parse/cleanup sentinels covered | 19/19 focused tests passed |
| 2.4 | `scripts/tests/test_generate_index.py` | Unit/fail closed | Focused transport safety net | Sensitive returned IDs and external details appeared in exceptions/logs | Identity/review/transport failures use stable application codes | No model output or external message/class is observable | 58/58 script tests passed |
| 2.5 | `scripts/tests/test_generate_index.py` | Unit/refactor/compatibility | OpenAI 1.68.0 probe | N/A — behavior-preserving refactor | Minimum SDK and safe legacy caller contract preserved | Full project regression passes | 617 passed, 3 skipped |
| 3.1 | `scripts/tests/test_generate_index.py` | Pipeline | 65/65 correction baseline | Missing-validator pipeline case failed 1/8 and printed output before fix | 8/8 fail closed with no writes or print | Review/download/extraction/protocol/conversion/incomplete/schema/validator paths | Stable diagnostics expose no external payloads |
| 3.2 | `scripts/tests/test_generate_index.py` | Pipeline | 58/58 baseline | 3.1 tests and incomplete-batch case preceded code | Complete mappings accumulate; every failure returns nonzero | Validation precedes dry/local/S3 publication | Extracted `_publish_catalog()` gate |
| 3.3 | `scripts/tests/test_generate_index.py` | Integration | Failure gate green | Legacy success contract failed schema validation | Publication-shaped Unit 2 mappings pass | Four exact product/route pairs across two batches | Explicit S3-key mapping; pipeline conversion forbidden |
| 3.4 | `scripts/tests/test_generate_index.py` | Regression/refactor | 65/65 focused | Dry-run and missing-validator regressions failed before fixes | 66 focused and 644 project tests pass | Four targeted validator/conversion/schema probes pass | Ruff unavailable is environmental, not functional |

## Verification

- `uv run pytest scripts/tests/test_generate_index.py`: 44 passed.
- Focused Unit 1 selection: 14 passed, 30 deselected.
- `uv run ruff check scripts/generate_index.py scripts/tests/test_generate_index.py`:
  unavailable through `uv` (`Failed to spawn: ruff`; no substitution used).

## Deviations

- `build_product_entry()` temporarily accepts the existing trusted discovery mapping
  as well as `TrustedDocument` so Unit 1 remains autonomous before Units 2–3 replace
  the transport/pipeline. Routing fields always come from that trusted argument.

## Remaining

- None — ready for fresh SDD verify; Ruff availability remains an environmental warning.

## Unit 3 Verification

- `uv run pytest scripts/tests/test_generate_index.py`: 66 passed.
- `uv run pytest`: 644 passed, 3 skipped.
- Validator/conversion/schema probes: 4 passed.
- Exact Ruff command unavailable (`Failed to spawn: ruff`); no fallback used.
- `git diff --check`: passed; intentional Unit 3 diff remains below 400 lines.
- Write atomicity ends at the pre-write gate: an S3 failure can follow a successful local save; no cross-store rollback or S3 transaction is claimed.

## Verification Correction: Deep Structured Output Closure

Fresh verification found that `dict[str, Any]` generated open technical-parameter
objects. Unit 1 now represents dynamic parameters as closed typed `name`/`value`
pairs and converts them to publication mappings only in `build_product_entry()`.

### Additional TDD Cycle Evidence

| Scope | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Deep extraction-schema closure | `scripts/tests/test_generate_index.py` | Unit/schema contract | 44/44 fresh baseline | 4 failed, 5 passed: recursive schema check exposed `additionalProperties=true`; pair payloads and nested error locations failed | 14/14 focused DTO/classification/conversion tests passed | Root, document, product, variant, technical parameter, common/key parameter pairs, scalar string/number values, and zero variants covered | Extracted recursive schema assertion helper; 14/14 focused tests remained green |

### Updated Verification

- Recursive `ExtractionBatch.model_json_schema()` inspection: 5 object nodes;
  root plus all `$defs` objects have `additionalProperties: false`.
- `uv run pytest scripts/tests/test_generate_index.py`: 51 passed.
- `uv run ruff check scripts/generate_index.py scripts/tests/test_generate_index.py`:
  still unavailable through `uv` (`Failed to spawn: ruff`; no substitution used).
- `git diff --check`: passed.
- Current tracked code+tests diff: 615 additions + 18 deletions = 633 changed
  lines. This exceeds 400 lines and has no `size:exception`; the orchestrator must
  subdivide the approved `stacked-to-main` delivery before PR creation.
