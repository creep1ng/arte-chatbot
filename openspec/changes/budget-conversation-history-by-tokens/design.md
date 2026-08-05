# Design: Complete Token-Budgeted Conversation History
## Approach and decisions
Preserve merged PRs #285–#288, #292, and replay PR #298. File Input count and create
reuse the same local model/instructions/`input_file`/`input_text`/reasoning mappings;
the parity test compares every count kwarg with the corresponding create value.
Create alone adds `max_output_tokens` and non-token-bearing `prompt_cache_key`.
The canonical implementation uses shared mappings rather than a request-shape type.

Resolve registry before count. `input_limit=min(hard_cap,floor(window*ratio))-
output_reserve`; accept `count <= limit`. Unknown model, missing counter, malformed/
negative count, API failure, or excess rejects before create; upload cleanup stays in
`finally`. Rejected alternatives: byte estimates/fail-open and independently built
payloads. Logs expose model, registry, numbers, acceptance, reason, exception type;
never content, paths, file/session IDs, previews, or exception bodies.

Replay pins model snapshot, registry/config/prompts/tools, 20 Spanish exchanges,
`tiktoken` 0.13.0/`o200k_base` source hash, and SHA-256-indexed audited counts; a
fixture hash binds all inputs. Runtime never loads encoding/network/API keys and
fails closed outside corpus; canonical JSON has no timestamp. Rejected: vendored
tokenizer, live replay, remembered totals.

## Flow/contracts
`PDF -> byte guard -> upload -> shape -> count -> policy -> reject | create -> cleanup`.
`replay.json -> pinned counter -> production selector -> canonical results.json`.
The preflight maps canonical request values into `responses.input_tokens.count`;
the decision records model, input limit/count, accepted/reason, and registry version.

## Files, tests, rollout
Backend preflight and replay fixture/generator/tests already live on main. Evidence v3
adds only generated results and the byte contract from `main@da46cbf` (321 lines).
Defaults v3 adds README/env/OpenSpec from evidence v3 (≤330 lines before verify; up to
70 reserved for the fresh report). PR #299 owns open latency/routing changes and does
not alter this chain. Tune only from telemetry; rollback either v3 slice independently
and keep File Inputs fail closed. No migration. Open questions: none.
