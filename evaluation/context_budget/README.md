# Reproduce context-budget evidence

This offline replay measures the existing preliminary defaults; it does not tune
them or call a provider. The committed Spanish fixture pins 20 exchanges, the
`gpt-5.4-nano-2026-03-17` registry snapshot, `o200k_base`, tokenizer source/hash,
and audited SHA-256-indexed counts.

PR #298 merged the replay and its CLI into `main@da46cbf`. Evidence v3 adds only
the canonical `results.json` and its byte-equality test; defaults/docs v3 follows
on that evidence commit. PR #299 keeps latency and tool-routing changes separate.

## Run and verify

```bash
uv run pytest evaluation/context_budget/test_simulation.py -q
uv run python -m evaluation.context_budget.simulation | \
  cmp - evaluation/context_budget/results.json
```

The method validates fixture integrity and registry pins, selects the newest
contiguous complete-turn suffix with production code, counts each request and
response from the audited corpus, and serializes canonical UTF-8 JSON without a
timestamp. Tests run generation in fresh processes with empty tokenizer caches,
network denied, and provider API-key reads guarded.

## Read the metrics correctly

| Metric | Tokens | Meaning |
|---|---:|---|
| Final context input | 1,368 | One hypothetical request after all 20 exchanges; 20 selected turns. |
| Cumulative input | 14,497 | Sum of input tokens across the 20 actual replay requests. |
| Cumulative output | 510 | Sum of the 20 recorded responses. |
| Cumulative total | 15,007 | Input plus output consumed by the whole replay. |

Final context is request size, NOT cumulative consumption. Per-turn values and
running totals are in `results.json`.

## Why these six preliminary defaults

- **10% ratio:** model-relative ceiling (40,000 of the pinned 400,000-token window)
  that still adapts if a registered model window changes.
- **32,000 hard cap:** the effective gross cap (8% of that window), over 23× the
  1,368-token final simulated input, while bounding cost and latency.
- **2,000 output reserve:** equals `LLM_MAX_OUTPUT_TOKENS`, so output is reserved
  once before input admission.
- **12,000 non-history reserve:** the first no-history replay request used 109 input
  tokens; the larger reserve conservatively covers system prompt, tools, current
  input, framing, and agentic variation before history is selected.
- **5 MiB File Input cap:** limits upload abuse/cost before provider upload; bytes
  do not estimate extracted PDF tokens, so exact provider token preflight remains
  mandatory.
- **20-turn ceiling:** bounds storage/query and selection work; this replay confirms
  all 20 fit, not that 20 is optimal for production conversations.

These are preliminary safety defaults, not production recommendations. This
text-only fixture cannot validate real PDFs, provider extraction, reasoning tokens,
traffic mix, latency, quality, or cost. Revisit every default only with production
telemetry; never weaken fail-closed File Input preflight from this replay.
