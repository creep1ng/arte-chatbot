# Delta: Context Budget Management
## ADDED Requirements
### Requirement: Versioned Model Budget Policy
The system MUST use an immutable versioned registry. Gross cap MUST be the lesser of
hard cap and context ratio; output MUST be subtracted once; history MUST also
subtract the greater of measured non-history input and its reserve.
#### Scenario: Known model derives the effective history budget
- **GIVEN** registered limits/settings **WHEN** calculated **THEN** reserves are conservative and output is reserved once.
#### Scenario: Unknown capability fails closed
- **GIVEN** absent model/tokenizer **WHEN** admission runs **THEN** no history or File Input is admitted.

### Requirement: Complete Recent History Selection
The system MUST return chronologically the newest contiguous suffix of complete
turns fitting token budget and `max_turns`, never skipping an oversized newer turn.
#### Scenario: Short and oversized histories
- **GIVEN** fitting history or oversized newest turn **WHEN** selected **THEN** all fit or no older turn bypasses the newest.
#### Scenario: Exact boundary, Unicode, and sources
- **GIVEN** Spanish/Unicode turns and sources **WHEN** exact/one-over sizes run **THEN** exact is included, one-over excluded, and content/sources remain intact and counted.
#### Scenario: Turn ceiling
- **GIVEN** more fitting turns than `max_turns` **WHEN** selected **THEN** only newest `max_turns` return chronologically.

### Requirement: Conservative Request Accounting
The system MUST account for system, tools, current input, history, output, framing,
and File Inputs. File admission MUST count the exact model, instructions, file/text
input, and reasoning fields used by create.
#### Scenario: Exact File Input boundary
- **GIVEN** a registered counted request **WHEN** count plus output is at/below gross cap **THEN** create is allowed; one-over is rejected before create.
#### Scenario: Unprovable File Input safety
- **GIVEN** unknown model or unavailable/failed counter **WHEN** admission runs **THEN** it fails closed and create is not called.
#### Scenario: Count and create remain equivalent
- **GIVEN** an admitted request **WHEN** payloads are compared **THEN** every token-relevant field is identical.

### Requirement: Content-Safe Budget Observability
Decisions MUST log only metrics/reason codes, never content, PII, source paths, file
or session IDs, previews, or exception bodies.
#### Scenario: Success and failure logs are safe
- **GIVEN** secret markers **WHEN** admission succeeds/fails **THEN** logs include metrics without markers/exception text.

### Requirement: Reproducible Budget Evidence
The repository MUST replay 20 Spanish messages/responses deterministically without
API keys using pinned registry/tokenizer inputs, reporting each request's input,
output, total, cumulative values, final context, and whole-session consumption.
#### Scenario: Replay regenerates identically
- **GIVEN** committed 10–30-word user messages **WHEN** run repeatedly offline **THEN** all 20 metrics and report bytes are identical.
#### Scenario: Context and consumption are not conflated
- **GIVEN** completed replay **WHEN** reviewed **THEN** final context differs from cumulative input/output/total.

### Requirement: Preliminary Defaults Are Discoverable
Environment examples MUST label 10%, 32,000, 2,000 output reserve, 12,000
non-history reserve, 5 MiB File Input cap, and 20 turns as preliminary.
#### Scenario: Evidence qualifies default rationale
- **GIVEN** replay results **WHEN** defaults are justified **THEN** each is linked to evidence and production PDFs, reasoning, and telemetry remain validation caveats.
