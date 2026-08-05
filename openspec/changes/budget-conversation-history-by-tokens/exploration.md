## Exploration: budget-conversation-history-by-tokens
### State and gap
Issue #262 foundations were already merged and MUST NOT be rebuilt: PR #271 versioned
`gpt-5.4-nano` registry; #281 deterministic `tiktoken`; #285 validated 10%, 32,000,
2,000, 12,000, 5 MiB, and 20-turn defaults; #286 newest contiguous complete-turn
selection (chronological, sources counted, unknown capability fails closed, safe
metrics); #287 `/chat` wiring/first-iteration history; #237 bounded chronological
DynamoDB reads. PR #288 later supplied the byte guard and safe diagnostics.

Missing at exploration: exact extracted File Input count before create, safe failure
logs, and committed reproducible 20-exchange evidence/default rationale. A byte cap
cannot bound extracted tokens. Residual remembered totals (2,738/42 final request;
41,270/764 cumulative) were recovery clues only, not acceptable evidence.

### Affected areas
Reuse `model_capabilities.py`, `config.py`, `context_budget_config.py`, and
`context_budget.py`; change File Input policy/client/tests; add
`evaluation/context_budget/`; document relevant `.env.example` values. Preserve
unrelated `.kilo/package-lock.json` and `.kilocode/package-lock.json` bytes.

### Approaches and recommendation
1. **Complete stacked-to-main chain (chosen, medium):** after #288, add shared-shape
exact preflight, then pinned offline replay/report/rationale. Preserves reviewed
architecture, safety, and ≤400-line slices; adds provider availability coupling.
2. **Treat reserve/bytes as sufficient (rejected, low):** smaller but cannot prove
PDF token safety and omits evidence.
3. **Provider-count every request (rejected, high):** maximal parity but replaces
merged deterministic selection and adds latency/network coupling.

Count the exact model/instructions/file/text/reasoning create shape; subtract output
once; accept the exact boundary; reject one-over, unknown capability, unavailable or
failed count before create; never log content, paths, IDs, sessions, previews, or
exception bodies. Replay pinned Spanish 10–30-word inputs twice offline and separate
final context from cumulative consumption. Defaults remain preliminary pending real
PDF/reasoning/quality/cost/latency telemetry.

### Risks/readiness
Count/create drift requires one shape and parity tests; outage intentionally reduces
File Input availability; fixture changes require audited count/hash regeneration;
framing beyond nine turns needs boundary coverage. Forecast exceeds 400, therefore
`stacked-to-main`. Ready for a completion proposal; close #262 only when every
criterion maps to merged code, tests, evidence, and qualified rationale.
