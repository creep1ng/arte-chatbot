# Design: Complete Token-Budgeted Conversation History
## Approach and decisions
Preserve #285–#288. A frozen `FileInputRequestShape` feeds exact token-bearing
model/instructions/`input_file`/`input_text`/reasoning mappings to both count/create;
create alone adds unsupported-by-count `max_output_tokens` and non-token-bearing
`prompt_cache_key`. `InputTokenCounter` isolates OpenAI; provider-independent
`file_input_budget.py` returns immutable metric-only decisions.

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
Counter contract: `count(FileInputRequestShape) -> int`; decision records model,
input limit/count, accepted/reason, and registry version.

## Files, tests, rollout
Backend budget/client/tests plus SDK lock support; replay fixture/generator/tests;
generated results; README/env/OpenSpec. Unit boundaries/failures/no-create, complete
mapping parity, sentinel-log safety, and two cold offline byte comparisons. Four
`stacked-to-main` slices target updated main: preflight, generator, evidence, then
docs/change record. Tune only from telemetry; rollback each independently and keep
File Inputs fail-closed. No migration. Open questions: none.
