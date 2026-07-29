# Apply Progress: Preserve PDF Extraction Identity

## Batch

- Mode: Strict TDD
- Delivery: stacked-to-main
- Current unit: Unit 1 implementation complete; PR separation pending
- Scope: tasks 1.1–1.5 only
- Verification status: PASS WITH WARNINGS
- PR gate: split 633-line Unit 1 into PR 1A/1B/1C before commit or PR
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

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.1 | `scripts/tests/test_generate_index.py` | Unit | 30/30 baseline | ImportError for missing typed boundary; 0 collected | 9/9 identity tests passed in 1.2 | Exact and out-of-order success plus missing, extra/unknown, and duplicate failures | 14/14 Unit 1 tests passed after helper extraction |
| 1.2 | `scripts/tests/test_generate_index.py` | Unit | 30/30 baseline | Tests from 1.1 preceded production code | 9/9 identity tests passed | Closed root/nested DTOs and multiple reconciliation branches | 14/14 Unit 1 tests passed after `_validate_identity_sets()` extraction |
| 1.3 | `scripts/tests/test_generate_index.py` | Unit | 9/9 identity tests | 4 failed and 1 passed before classification/conversion | 5/5 classification/conversion tests passed in 1.4 | Normal variants, zero, multiple, mismatch, and trusted precedence | 14/14 Unit 1 tests passed after typed helper consolidation |
| 1.4 | `scripts/tests/test_generate_index.py` | Unit | 9/9 identity tests | Tests from 1.3 preceded production code | 5/5 classification/conversion tests passed | Cardinality and routing mismatch take distinct paths | 14/14 Unit 1 tests passed after `_review_reasons()`/routing helper cleanup |
| 1.5 | `scripts/tests/test_generate_index.py` | Unit/refactor | 44/44 approval baseline | N/A — behavior-preserving refactor | 14/14 focused tests passed | Existing 14-case Unit 1 matrix preserved | 44/44 final tests passed |

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

- Separate completed Unit 1 into PR 1A/1B/1C before any commit or PR.
- Unit 2 / tasks 2.1–2.5: Responses API and real File Inputs.
- Unit 3 / tasks 3.1–3.4: fail-closed pipeline publication gate.

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
