# Catalog PDF Extraction Integrity Specification

## Purpose

Define trustworthy identity, reconciliation, review, and publication for PDF catalog extraction.

## Requirements

### Requirement: Trusted expected identities

The system MUST establish exactly one unique, application-owned identity per source PDF. Source path, category, and subcategory MUST come only from trusted records, never model output.

#### Scenario: Trusted source fields are preserved

- GIVEN a source identity mapped to trusted source fields
- WHEN schema-valid extraction claims different source fields
- THEN the system MUST retain the trusted values

#### Scenario: Expected identities are not unique

- GIVEN two source PDFs assigned the same expected identity
- WHEN extraction begins
- THEN the run MUST fail closed
- AND MUST publish no catalog output

### Requirement: Order-independent source association

The system MUST associate extracted products with sources by identity, independent of order.

#### Scenario: Complete batch returned out of order

- GIVEN distinct expected identities for a complete PDF batch
- WHEN one valid result per identity arrives in a different order
- THEN every result MUST reconcile to its matching trusted source
- AND order alone MUST NOT change publication eligibility

### Requirement: Exact identity reconciliation

Before conversion or publication, returned identities MUST be unique and exactly equal the expected set.

#### Scenario: Identity set matches exactly

- GIVEN unique expected and returned identity sets
- WHEN both sets contain the same identities
- THEN reconciliation MUST succeed

#### Scenario: Identity anomaly

- GIVEN a response with a missing, extra, unknown, or duplicate identity
- WHEN reconciliation runs
- THEN the run MUST fail closed
- AND MUST publish no partial or fallback entries

### Requirement: Structured output trust boundary

Structured Outputs MUST guarantee shape only, not semantic correspondence between content and source identity.

#### Scenario: Schema-valid suspicious mismatch

- GIVEN schema-valid extracted content whose product evidence conflicts suspiciously with its trusted source
- WHEN semantic classification runs
- THEN the source MUST be classified `needs_review`
- AND MUST NOT be published

### Requirement: Product cardinality classification

A single series with variants MUST be normal success. Multi-product, non-product, or suspicious mismatch results MUST be `needs_review` and MUST NOT be published.

#### Scenario: Series with variants

- GIVEN a reconciled PDF describing one product series with multiple variants
- WHEN its extraction is complete and valid
- THEN it MUST be treated as a normal successful extraction

#### Scenario: Review-only source

- GIVEN a reconciled PDF classified as multi-product, non-product, or suspiciously mismatched
- WHEN publication eligibility is evaluated
- THEN it MUST remain `needs_review`
- AND no entry from that source MUST be published

### Requirement: Fail-closed extraction

The system MUST fail closed on refusal, incomplete output, schema/parse failure, or API failure, without inferred, partial, stale, or fallback entries.

#### Scenario: Model response cannot be accepted

- GIVEN a refusal, incomplete response, or schema or parse failure
- WHEN the batch is evaluated
- THEN the run MUST fail
- AND MUST publish no output from the batch

#### Scenario: Extraction API fails

- GIVEN the extraction API returns an error or no acceptable response
- WHEN the batch is evaluated
- THEN the run MUST fail closed
- AND MUST publish no fallback output

### Requirement: Publication gate

The system MUST publish only after successful reconciliation, completeness checks, semantic classification, conversion, and validation. It MUST NOT publish `needs_review` sources.

#### Scenario: Fully valid publication

- GIVEN all identities reconcile exactly and every candidate is complete, eligible, converted, and valid
- WHEN publication is requested
- THEN only validated eligible entries MUST be published

#### Scenario: Validation fails after reconciliation

- GIVEN identities reconcile but conversion or publication validation fails
- WHEN publication is requested
- THEN the run MUST fail closed
- AND MUST publish no invalid or partial output
