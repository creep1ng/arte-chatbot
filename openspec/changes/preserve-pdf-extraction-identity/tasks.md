# Tasks: Preserve PDF Extraction Identity

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | Unit 1 verified: 633 code+tests; Units 2–3 pending |
| Suggested split | PR 1A → PR 1B → PR 1C → PR 2 → PR 3 |
| Delivery strategy | ask-on-risk resolved; no `size:exception` |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|---|---|---|---|
| 1A | Closed contract: `ClosedDTO`, extraction DTOs, `TechnicalParameter`, recursive/deep-extra tests | PR 1A | Target `main`; tests; autonomous rollback |
| 1B | Trusted reconciliation: `TrustedDocument`, opaque IDs, exact sets, order/anomaly tests | PR 1B | `main` after 1A; tests; autonomous rollback |
| 1C | Review classification and trusted conversion: cardinality, mismatch, conversion, routing | PR 1C | `main` after 1B; tests; autonomous rollback |
| 2 | Responses API and File Inputs | PR 2 | `main` after 1C; tests; autonomous rollback |
| 3 | Publication gate | PR 3 | `main` after PR 2; tests; autonomous rollback |

## Phase 1: Typed Identity and Reconciliation (Unit 1)

- [x] 1.1 RED — Test closed DTO rejection, duplicate expected IDs, order-independent exact matching, and returned-ID anomalies in `scripts/tests/test_generate_index.py`.
- [x] 1.2 GREEN — Implement closed extraction DTOs, `TrustedDocument`, exceptions, opaque-ID trusted map, and exact reconciliation in `scripts/generate_index.py`.
- [x] 1.3 RED — Test trusted routing precedence, variants, and `needs_review` for zero, unrelated, or mismatched products.
- [x] 1.4 GREEN — Implement cardinality/mismatch classification and trusted-only `build_product_entry()` conversion in `scripts/generate_index.py`.
- [x] 1.5 REFACTOR — Consolidate typed fixtures/helpers while preserving focused reconciliation tests in both files.

## Phase 2: File Inputs and Responses API (Unit 2)

- [x] 2.1 RED — Mock `client.files` and `client.responses.parse` to require adjacent opaque-ID `input_text` plus real `input_file` content and order-independent parsed output.
- [x] 2.2 GREEN — Replace Chat Completions JSON mode in `extract_metadata_batch()` with uploads, trusted map, `responses.parse(..., text_format=ExtractionBatch)`, reconciliation, and `finally` cleanup.
- [x] 2.3 RED — Cover refusal, incomplete status/reason, absent parsed output, schema/parse error, API error, and warning-only cleanup failure.
- [x] 2.4 GREEN — Fail closed with source-specific diagnostics for every unacceptable response; never synthesize fallback entries.
- [x] 2.5 REFACTOR — Verify the minimum OpenAI constraint; update `pyproject.toml` and `uv.lock` only if `responses.parse` requires it.

## Phase 3: Publication Gate (Unit 3)

- [ ] 3.1 RED — Add pipeline tests proving `needs_review`, download/extraction/protocol, conversion, and schema-validation failures return non-zero and call neither `save_local()` nor `upload_to_s3()`.
- [ ] 3.2 GREEN — Update `run_pipeline()` to accumulate only complete normal batches, validate the full catalog, and publish atomically only after every gate succeeds.
- [ ] 3.3 RED/GREEN — Adapt the successful local pipeline test to keyed results and prove only validated eligible entries publish with trusted routing fields.
- [ ] 3.4 REFACTOR — Run `uv run pytest scripts/tests/test_generate_index.py` and `uv run ruff check scripts/generate_index.py scripts/tests/test_generate_index.py`; remove positional/fallback paths.
