# Tasks: Complete Token-Budgeted Conversation History
## Review Workload Forecast
Four `stacked-to-main` slices target updated main, ≤400 changed lines each; combined
estimate 1,250–1,540. Estimates/risk: S1 preflight 330–390/high; S2 replay 300–380/
medium; S3 evidence 320–350/medium; S4 docs/change record 300–400/high. Policy
`auto-forecast`, execution `auto`; decision needed: no; chained: yes; overall risk:
high. Roll back only the current autonomous slice.

## Slice 0: Apply Precondition
- [x] 0.1 Preserve both unrelated package locks; update to main `84850bf+`, verify ancestry/#288.
- [x] 0.2 Record status/byte-guard tests; rollback base update while preserving lock bytes.
## Slice 1: Exact File Input Preflight
- [x] 1.1 RED exact/one-over, unknown/invalid, safe-log, count failure/unavailable, no-create, full parity tests.
- [x] 1.2 GREEN immutable decision/shape, protocol/adapter, shared mapping, count-before-create.
- [x] 1.3 GREEN constrain OpenAI count support; retain create-only output/cache and cleanup.
- [x] 1.4 REFACTOR focused tests/lint/≤400; unsafe never creates/logs content, paths, IDs, sessions, exceptions.
## Slice 2: Deterministic Offline Replay
- [x] 2.1 RED 20 Spanish 10–30-word inputs, pins, boundary, metrics, offline/API-key-free/stable bytes.
- [x] 2.2 GREEN fixture and pure generator using registry/audited `tiktoken` 0.13.0 counts.
- [x] 2.3 REFACTOR pure load/count/serialize; run twice; rollback without production changes.
## Slice 3: Executable Evidence
- [x] 3.1 RED regenerated canonical bytes must equal committed `results.json`.
- [x] 3.2 GREEN generate results; defer rationale/env to Slice 4.
- [x] 3.3 REFACTOR regenerate twice; backend/replay tests, mypy/Ruff/diff; 321 lines vs `f18a02e`.
## Slice 4: Defaults and Change Record
- [x] 4.1 RED require all six rationales, PDF/reasoning/telemetry caveats, and matching env examples.
- [x] 4.2 GREEN reproducible README and preliminary `.env.example` defaults.
- [x] 4.3 REFACTOR retain every criterion/scenario/decision/forecast/task/progress in six compact artifacts; strict validate, focused tests, exact regeneration, quality/diff; docs/config/OpenSpec ≤340 before verify.
