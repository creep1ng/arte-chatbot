# Design: Preserve PDF Extraction Identity

## Technical Approach

Replace positional JSON-mode extraction with a typed, keyed batch boundary in
`scripts/generate_index.py`. The application assigns every PDF an opaque identity,
sends every uploaded PDF as a Responses API File Input, reconciles the parsed result
against trusted inputs, converts only normal results, and validates the complete
published catalog before any write. The spec was not present during design; this
implements the proposal and exploration invariants.

## Architecture Decisions

| Decision | Choice and rationale | Rejected alternative |
|---|---|---|
| Separate contracts | Closed Pydantic v2 extraction DTOs (`ConfigDict(extra="forbid")`) model required fields and nullable metadata; `docs/schemas/catalog_index.schema.json` remains the publication contract. Its `allOf`/`if`/`then` composition is unsuitable as a strict Structured Output, and shape validation does not establish provenance. | Reusing the publication schema or loose `dict`/JSON mode. |
| Trusted identity | Create a random opaque `document_id` (UUID hex is sufficient) per batch item and a `dict[str, TrustedDocument]` containing immutable `pdf_info`, `s3_key`, and uploaded `file_id`. Only this map supplies `ruta_s3`, `categoria`, and `subcategoria`. | File IDs, list positions, filenames, or model-echoed paths as authority. |
| Exact reconciliation | Index parsed documents by ID; reject duplicate, missing, unknown, or extra IDs before converting anything. Set equality makes result order irrelevant. An echoed source/category assertion may only trigger review or protocol diagnostics. | `zip()` or partial batch acceptance. |
| Outcome policy | `normal` requires exactly one product series with at least one variant. Zero products, unrelated multiple products, or suspicious source/content mismatch become `needs_review`; one series with several variants remains normal. Any review or protocol/transport failure blocks the whole run and all publication. | Fabricated fallback entries or publishing unaffected batch fragments. |

## Data Flow

```text
PDF bytes -> upload -> trusted_map[document_id]
                     -> Responses.parse(input_text ID + input_file pairs)
                     -> typed envelope -> exact reconciliation
                     -> normal DTO conversion -> catalog schema validation
                     -> atomic local save / S3 upload
```

`extract_metadata_batch()` builds one user content list with repeated adjacent
`{"type":"input_text","text":"document_id: ..."}` and
`{"type":"input_file","file_id": ...}` items, then calls
`client.responses.parse(model=model, instructions=EXTRACTION_SYSTEM_PROMPT,
input=[...], text_format=ExtractionBatch)`. Uploaded Files are deleted in `finally`.

## Interfaces / Contracts

All types stay in `scripts/generate_index.py` to match the current single-script
boundary:

```python
class ExtractionStatus(str, Enum):
    NORMAL = "normal"
    NEEDS_REVIEW = "needs_review"

class DocumentExtraction(ClosedDTO):
    document_id: str
    status: ExtractionStatus
    products: list[ExtractedProduct]
    review_reasons: list[str]

class ExtractionBatch(ClosedDTO):
    documents: list[DocumentExtraction]

@dataclass(frozen=True)
class TrustedDocument:
    s3_key: str
    pdf_info: dict[str, Any]
    file_id: str
```

`reconcile_batch(parsed, trusted_map) -> list[tuple[ExtractedProduct,
TrustedDocument]]` either returns a complete normal batch or raises a typed
`ExtractionProtocolError` / `ExtractionNeedsReview`. `build_product_entry()` accepts
model-owned product fields plus the trusted document; it must never read routing
fields from model output.

Before reconciliation, reject any refusal content, `response.status != "completed"`
(log `incomplete_details.reason`), missing `output_parsed`, Pydantic/schema failure,
or OpenAI API error. `run_pipeline()` logs source IDs/keys, returns non-zero, and
does not call `save_local()` or `upload_to_s3()`. Cleanup failure is warning-only.

## File Changes

| File | Action | Description |
|---|---|---|
| `scripts/generate_index.py` | Modify | DTOs, Responses File Inputs, trusted map, reconciliation, conversion, fail-closed orchestration |
| `scripts/tests/test_generate_index.py` | Modify | DTO, request, reconciliation, failure, and publication-boundary tests |
| `pyproject.toml`, `uv.lock` | Conditional | Raise OpenAI minimum only if the declared `>=1.68.0` lacks the verified helper |
| `docs/schemas/catalog_index.schema.json` | None | Existing final validator |

## Testing Strategy

Unit tests cover closed DTO rejection; out-of-order success; missing, extra/unknown,
and duplicate IDs; trusted routing-field precedence; normal series variants; and
no-product, multi-product, and mismatch review. Mocked SDK tests assert real
`input_file` items and refusal, incomplete, absent parsed output, API, and schema
failures. Pipeline tests assert non-zero exit and zero local/S3 writes on every
failure, plus conversion followed by successful full-schema validation.

## Migration / Rollout

Run against representative local PDFs with `--local-only` and a disposable output,
then compare entries and enable S3 publication. The lock currently resolves OpenAI
2.30.0/Pydantic 2.12.5, but `pyproject.toml` permits OpenAI 1.68.0; verify
`responses.parse(..., text_format=...)` in the minimum environment and raise the
constraint if incompatible. Roll back the code/dependency change and preserve the
last valid index; one-PDF requests remain the operational fallback. No data
migration is required.

## Open Questions

None.
