## Exploration: budget-conversation-history-by-tokens
### Canonical state and remaining gap
Issue #262 foundations are merged: PRs #271/#281/#285–#288 and #292 provide the
registry, deterministic counting, preliminary defaults, complete-turn selection,
`/chat` wiring, byte guard, and exact fail-closed File Input preflight. PR #298 then
merged the deterministic replay and retained its module CLI in `main@da46cbf`.

Main still lacks durable `results.json`, its exact-byte contract, default rationale,
environment examples, and this change record. PR #299 remains OPEN as an independent
latency/tool-routing slice; it is not evidence or documentation work and is not
duplicated here. Unrelated package-lock bytes must remain unstaged and unchanged.

### Minimal completion chain
1. **Evidence v3:** branch `docs/context-budget-evidence-262-v3` from
   `main@da46cbf`; add only the 312-line report and 9-line equality test (321 lines).
2. **Defaults v3:** branch `docs/context-budget-defaults-262-v3` from evidence v3;
   add `.env.example`, README, and compact OpenSpec, ≤330 lines before fresh verify.

Treating byte limits as token estimates remains rejected. The replay runs offline on
20 pinned Spanish exchanges, distinguishes final context from cumulative use, and
does not justify production tuning by itself.

### Risks and readiness
Provider counting can reduce File Input availability by design. Count/create drift is
controlled by reusing the same model/instructions/input/reasoning mappings and by
parity tests, not by a frozen request-shape type. Fixture edits require audited counts
and a new fixture hash. Real PDFs, extraction, reasoning, latency, quality, cost, and
traffic still require production telemetry. The two v3 slices are ready for fresh
verification; no PR closure follows from this reconstruction.
