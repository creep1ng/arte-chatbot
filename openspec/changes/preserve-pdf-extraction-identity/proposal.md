# Proposal: Preserve PDF Extraction Identity

## Intent

Prevent catalog corruption by preserving application-owned PDF identity through batched extraction and rejecting responses that cannot be reconciled exactly to trusted sources.

## Scope

### In Scope
- Use closed Pydantic Structured Output DTOs and real PDF File Inputs.
- Generate opaque `document_id` values mapped to `pdf_info`, S3 key, and OpenAI file ID.
- Reconcile unique identities regardless of order; fail closed on identity anomalies and refusal, incomplete, parse/schema, or API failures.
- Source `ruta_s3`, category, and subcategory only from the trusted map.
- Mark no-product, multi-product, or suspicious mismatch outcomes `needs_review` and block publication.
- Test reconciliation and failure policy.

### Out of Scope
- Durable `needs_review` storage, UI, or S3 queue.
- Published schema redesign, automatic multi-product curation, backend search, or unrelated LLM calls.
- One-PDF-per-request, retained as a fallback.

## Capabilities

### New Capabilities
- `catalog-pdf-extraction-integrity`: Typed File Input extraction, trusted identity reconciliation, review classification, and fail-closed publication.

### Modified Capabilities
- None. Existing specs omit catalog generation requirements.

## Approach

Build a keyed extraction envelope. Place each opaque ID beside its `input_file`, parse with Structured Outputs, and require exact ID set equality plus uniqueness before conversion. Accept arbitrary order. Treat one series with variants as normal; classify multi-product, no-product, and suspicious mismatches as `needs_review`. Structured Outputs enforces shape, not truth; trusted fields never come from the model.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `scripts/generate_index.py` | Modified | DTOs, File Inputs, identity map, reconciliation, failure policy |
| `scripts/tests/test_generate_index.py` | Modified | Reconciliation and review-boundary coverage |
| `docs/schemas/catalog_index.schema.json` | Unchanged | Publication validator |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Schema-valid metadata is semantically swapped | Medium | Detect suspicious mismatches; block publication; retain single-PDF fallback |
| Extraction DTO diverges from publication schema | Medium | Separate contracts; validate conversion before publication |
| Fail-closed runs publish no update | Medium | Emit source-specific diagnostics and return failure |
| Change exceeds 400 review lines | Medium | Keep helpers focused; ask before splitting |

## Rollback Plan

Revert the extraction/reconciliation change; never publish failed or partially reconciled output.

## Dependencies

- Approved exploration in `exploration.md`.
- Existing Pydantic v2 and OpenAI SDK; constrain the SDK only if required.

## Success Criteria

- [ ] Complete keyed batches reconcile correctly in any order.
- [ ] Missing, unknown/extra, and duplicate IDs produce no catalog entries.
- [ ] Refusal, incomplete, parse/schema, and API failures produce no fallback entries.
- [ ] Trusted source fields cannot be overwritten by model output.
- [ ] Series PDFs publish normally; no-product and multi-product outcomes are blocked as `needs_review`.
