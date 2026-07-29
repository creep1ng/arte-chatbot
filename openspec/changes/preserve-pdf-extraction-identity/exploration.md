## Exploration: preserve-pdf-extraction-identity

### Current State

`scripts/generate_index.py` discovers PDFs deterministically, downloads each batch,
and calls `extract_metadata_batch()`. The extraction function returns an unkeyed
`list[dict]`; `run_pipeline()` then associates results with source files through
`zip(extracted, pdf_bytes_list)`. This creates two silent corruption modes:
out-of-order results are assigned to the wrong PDF, while missing or extra results
are truncated by `zip()` without detecting cardinality drift. `ruta_s3`, category,
and subcategory are then copied from whichever positional `pdf_info` happened to
be paired with the extraction.

The current prompt asks for one JSON product per attached PDF and uses JSON mode
(`response_format={"type": "json_object"}`), which guarantees JSON syntax but not
schema adherence. The integration test explicitly mocks results in discovery
order and has no out-of-order, missing-result, extra-result, duplicate-identity,
or unknown-identity coverage.

There are two adjacent integrity problems relevant to the scope:

- Uploaded Files API IDs are mentioned in text, but the Chat Completions request
  does not include file content items. Official OpenAI File Inputs documentation
  requires each uploaded ID to be supplied as an actual `input_file` item (the
  current Responses API form). The identity fix must not preserve this omission.
- Batch extraction failures currently create basic fallback catalog entries;
  catalog schema errors are logged and publication continues. Those behaviors
  can turn uncertainty into apparently authoritative enterprise catalog data.

OpenAI Structured Outputs is applicable, but it solves shape rather than
provenance. Official documentation confirms schema adherence, native Pydantic
parsing, required fields, `additionalProperties: false`, and explicit refusal and
incomplete-response handling. It also states that structured values may still be
semantically wrong. Therefore a schema-valid `source_s3_key` is not evidence that
the metadata came from that PDF.

The published `docs/schemas/catalog_index.schema.json` cannot be reused directly
as a strict Structured Outputs schema: it contains unsupported composition and
conditionals (`allOf`, `if`/`then`) and optional fields. A separate extraction DTO
is needed, with all fields required, nullable fields where appropriate, closed
objects, and category alternatives nested below an object root. The existing
catalog schema remains the publication validator.

### Affected Areas

- `scripts/generate_index.py` — extraction request, typed response envelope,
  deterministic reconciliation, refusal/incomplete handling, review policy, and
  removal of positional `zip()` association.
- `scripts/tests/test_generate_index.py` — keyed out-of-order success plus missing,
  extra/unknown, and duplicate identity failures; refusal, incomplete, no-product,
  and multi-product review behavior should also be covered at the reconciliation
  boundary.
- `docs/schemas/catalog_index.schema.json` — publication contract consulted after
  reconciliation; no change is required for the narrow identity fix.
- `pyproject.toml` / `uv.lock` — the repository already has Pydantic v2 and a
  current OpenAI SDK lock, so native parsed Structured Outputs should not require
  a new library; an SDK constraint change is only needed if implementation proves
  the used Responses/Pydantic helper unavailable.

### Approaches

1. **Structured batch envelope plus deterministic identity reconciliation** —
   Generate an application-owned opaque `document_id` for each batch input, keep
   a trusted `document_id -> pdf_info` map, place the ID adjacent to each real
   `input_file`, and require one typed document result per ID. Reconcile by exact
   set equality and uniqueness, not order. Derive `ruta_s3` only from the trusted
   map. If the model also echoes `source_s3_key`, treat it as an assertion that
   must exactly match the map, never as the source of truth.
   - Pros: directly eliminates positional coupling; accepts out-of-order output;
     preserves batching economics; gives Pydantic/schema validation and explicit
     per-source traceability; supports deterministic missing/extra/duplicate tests.
   - Cons: cannot prove semantic attribution when a model places PDF A's content
     under PDF B's valid ID; requires a separate strict extraction schema and
     Responses API refusal/incomplete handling; batching still increases prompt
     complexity.
   - Effort: Medium

2. **One PDF per Structured Outputs request** — Send exactly one `input_file` and
   parse one typed extraction response; attach `pdf_info` in application code and
   never ask the model to choose a source identity.
   - Pros: strongest source isolation; no cross-document ordering/cardinality
     problem; simplest semantic attribution and retry behavior.
   - Cons: up to one request and schema processing path per PDF, increasing
     latency, request count, cleanup operations, and likely cost; gives up the
     existing batch-size optimization; the issue's batch anomaly tests become
     reconciliation-unit tests rather than normal request behavior.
   - Effort: Medium

3. **Keyed JSON mode without Structured Outputs** — Keep the current API shape,
   add `document_id` or `source_s3_key` to each JSON result, and manually validate
   IDs/cardinality before building entries.
   - Pros: smallest API migration and low implementation effort; fixes `zip()` if
     validation is complete.
   - Cons: JSON mode does not guarantee the required identity/status fields or
     closed schema; more parsing/retry code; preserves the current missing File
     Input attachment unless separately corrected; weaker foundation for an
     enterprise data asset.
   - Effort: Low

4. **Structured batch with per-PDF retry on protocol anomaly** — Use Approach 1
   normally, but reject an anomalous batch and retry each expected PDF through
   Approach 2 before deciding the run outcome.
   - Pros: keeps normal-case batching while obtaining source isolation when the
     batch contract breaks; avoids publishing fallback metadata.
   - Cons: more branches and tests; retries cannot detect a schema-valid semantic
     swap that did not trigger a protocol anomaly; worst-case request count is
     batch call plus one call per PDF.
   - Effort: Medium-High

### Recommendation

Use **Approach 1 as the core fix**, with the failure policy from Approach 4 but
without requiring automatic per-PDF retry in the first implementation. The
essential invariant is: **one trusted source record enters reconciliation and
exactly one uniquely keyed document envelope leaves it; order is irrelevant**.

Recommended extraction boundary:

- Application creates an opaque `document_id` for every PDF and stores its
  `pdf_info`, OpenAI file ID, and source key in a trusted batch map.
- The request includes each actual `input_file` next to text identifying its
  `document_id`; the typed root contains `documents: list[DocumentExtraction]`.
- Each document envelope has required fields such as `document_id`, `status`,
  `products`, and `review_reasons`. Nullable values model optional metadata.
- Reconciliation rejects duplicate IDs, unknown IDs, missing expected IDs, and
  any echoed source key that differs from the trusted map. Extra results are
  unknown IDs and are rejected. Out-of-order complete sets are accepted.
- `ruta_s3`, category, and subcategory always come from the trusted batch map.
  Model-extracted identity fields may support diagnostics but never overwrite
  source metadata.
- Refusal, incomplete response, missing parsed output, API failure, and strict
  schema failure produce no catalog entries for the affected batch. They must not
  fall back to fabricated basic entries.
- Catalog publication occurs only after deterministic reconciliation and existing
  catalog-schema validation; validation failure should stop publication rather
  than continue with a warning for newly extracted data.

`needs_review` policy for this change:

- A PDF representing one product series with multiple models remains one normal
  catalog product with multiple `variantes`; this is the established ADR-004
  model and is not a cardinality anomaly.
- A PDF containing multiple unrelated product series is one document envelope
  with multiple candidate products and `status=needs_review`. Do not publish the
  candidates automatically in this narrow fix because current IDs, idempotency,
  and curation semantics assume a product-series datasheet.
- A non-product PDF returns zero candidates with `status=needs_review`; do not
  create an `Unknown`/empty-variants catalog entry.
- Missing/extra/duplicate/unknown document identities are batch protocol failures,
  not reviewable successful products. Fail the affected batch (and preferably the
  run) or retry sources individually; never partially zip or publish it.
- A schema-valid but suspicious semantic mismatch (for example filename/source
  category versus extracted category/product) is `needs_review`, because
  Structured Outputs cannot establish factual correspondence.
- For the narrow issue, `needs_review` is an internal extraction/run outcome that
  blocks catalog publication and is emitted with source-key/reason diagnostics.
  A durable S3 review queue or catalog-schema status field is a follow-up design,
  not part of the identity repair.

In scope: real File Input attachment for this extraction call, strict extraction
DTOs, explicit trusted identity mapping, deterministic reconciliation, fail-closed
batch behavior, diagnostic traceability by source, and the requested tests.

Out of scope: redesigning the published catalog schema, adding a durable review
workflow/UI, automatic curation of multi-series PDFs, changing backend catalog
search, broad prompt-quality improvements, proving semantic truth from schema
validity, and migrating unrelated LLM calls.

### Risks

- A model can return the correct IDs with metadata semantically swapped between
  PDFs; deterministic reconciliation prevents positional corruption but cannot
  prove content provenance. One-PDF requests are the high-assurance fallback.
- The strict extraction schema may diverge from the publication schema. Keep DTOs
  intentionally separate, test conversion, and always run publication validation.
- Existing catalog schema composition is not accepted by Structured Outputs;
  trying to pass it unchanged will fail at the API boundary.
- Refusal/incomplete behavior differs from ordinary parsed output and must be
  tested explicitly or failures may re-enter generic fallback handling.
- Fail-closed behavior changes operational expectations: a run may produce no new
  catalog version until review/retry, which is safer but needs clear logs and a
  non-zero result.
- The complete fix may approach the 400-line review budget once DTOs and tests are
  included. Keep extraction/reconciliation helpers focused; ask before splitting
  because the configured chained-PR strategy is `ask-always`.

### Ready for Proposal

Yes. The proposal should adopt keyed batch reconciliation with Structured Outputs,
state that source identity is application-owned rather than model-authored, make
publication fail closed on protocol/schema anomalies, and keep durable review
workflow plus automatic multi-product curation out of scope.
