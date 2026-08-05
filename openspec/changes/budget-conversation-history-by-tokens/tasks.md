# Tasks: Complete Token-Budgeted Conversation History
## Review Workload Forecast
Merged preflight/replay work is not replayed. Two `stacked-to-main` v3 slices remain:
evidence is exactly 321 additions from `main@da46cbf`; defaults/docs targets evidence
and MUST stay ≤330 lines before verify, reserving up to 70 for the fresh report.
Decision needed: no; risk: low/medium; roll back only the current slice. PR #299 is an
open 174-line latency/routing PR against main and remains outside this chain.

## Slice 0: Apply Precondition
- [x] 0.1 Preserve both unrelated package locks; fetch and verify `main@da46cbf`.
- [x] 0.2 Record status/byte-guard tests; rollback base update while preserving lock bytes.
## Merged Slice 1: Exact File Input Preflight (#292)
- [x] 1.1 RED exact/one-over, unknown/invalid, safe-log, count failure/unavailable, no-create, full parity tests.
- [x] 1.2 GREEN immutable decision, shared count/create mappings, count-before-create.
- [x] 1.3 GREEN constrain OpenAI count support; retain create-only output/cache and cleanup.
- [x] 1.4 REFACTOR focused tests/lint/≤400; unsafe never creates/logs content, paths, IDs, sessions, exceptions.
## Merged Slice 2: Deterministic Offline Replay (#298)
- [x] 2.1 RED 20 Spanish 10–30-word inputs, pins, boundary, metrics, offline/API-key-free/stable bytes.
- [x] 2.2 GREEN fixture and pure generator using registry/audited `tiktoken` 0.13.0 counts.
- [x] 2.3 REFACTOR pure load/count/serialize plus retained module CLI; no production changes.
## V3 Slice 3: Executable Evidence
- [x] 3.1 RED regenerated canonical bytes must equal committed `results.json`.
- [x] 3.2 GREEN generate results; defer rationale/env to Slice 4.
- [x] 3.3 REFACTOR replay/test/diff from `da46cbf`; 321-line evidence boundary.
## V3 Slice 4: Defaults and Change Record
- [x] 4.1 RED require all six rationales, PDF/reasoning/telemetry caveats, and matching env examples.
- [x] 4.2 GREEN reproducible README and preliminary `.env.example` defaults.
- [x] 4.3 REFACTOR update all artifacts to #298 merged/#299 separate/v3 bases; strict, replay, scoped quality/diff; docs/config/OpenSpec ≤330 before fresh verify.
