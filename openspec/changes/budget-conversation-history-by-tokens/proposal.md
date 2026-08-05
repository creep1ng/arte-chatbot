# Proposal: Complete Token-Budgeted Conversation History
## Intent and scope
Close #262 without rebuilding PRs #271/#281/#285/#286/#287; #288 was merged after
exploration but absent from its original base. Add exact
`responses.input_tokens.count` File Input preflight, boundary/failure/parity/safe-log
tests, deterministic API-key-free 20-exchange Spanish replay/report/rationale, and
relevant `.env.example` examples. Out: replacing text selection, claiming production
PDF/reasoning validation, and unrelated lockfiles.

## Capability and approach
Add `context-budget-management`: model-aware complete history, exact fail-closed File
Input admission, content-safe observability, and reproducible evidence. One immutable
shape feeds count/create token fields; subtract output reserve once; reject excess,
unknown, unavailable, malformed, or failed counts before create. Pin replay inputs,
registry/tokenizer/counts and emit per-turn, final-context, and cumulative metrics.

## Delivery, impact, and rollback
`stacked-to-main` because combined work exceeds 400 lines: (1) exact preflight,
(2) replay generator, (3) generated evidence, (4) rationale/env/compacted OpenSpec;
each targets updated main and rolls back independently. Files: backend budget/client
and tests; `pyproject.toml`/`uv.lock`; `evaluation/context_budget/`; `.env.example`.
Dependency: merged #288 (`84850bf`) and official count endpoint. On outage disable
File Inputs/fail closed, never bypass preflight; text history remains available.

## Risks and success
Shared shape/parity tests prevent drift; fail-closed trades availability for safety;
pinned regeneration detects stale evidence. Success: unsafe/uncountable File Inputs
never create; parity and log safety are tested; report regenerates exactly; all six
defaults are discoverable, evidence-linked, preliminary, and telemetry-qualified.
