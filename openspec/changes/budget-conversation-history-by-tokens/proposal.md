# Proposal: Complete Token-Budgeted Conversation History
## Intent and scope
Complete the remaining issue #262 evidence and defaults without rebuilding merged
work. PR #292 owns exact File Input preflight; PR #298 owns the replay and CLI on
`main@da46cbf`. Add only canonical evidence, its equality test, rationale, matching
environment examples, and the compact change record. PR #299 latency/tool routing,
production tuning claims, and unrelated lockfiles are out of scope.

## Capability and approach
`context-budget-management` covers model-aware complete history, exact fail-closed
File Input admission, content-safe observability, and reproducible evidence. Count
and create reuse model/instructions/input/reasoning mappings; tests prove count kwargs
equal the token-bearing create subset. Create alone adds output/cache fields. Replay
pins inputs, registry, tokenizer, and counts and emits per-turn/final/cumulative data.

## Delivery, impact, and rollback
Use two `stacked-to-main` v3 slices: evidence targets `da46cbf` at 321 lines; defaults
targets the evidence commit and stays ≤330 lines before a fresh verify report, with up
to 70 additional report lines reserved. Each rolls back independently. PR #299 stays
open and separate. No force-push, duplicate replay, runtime code, or lockfile change.

## Risks and success
Shared mappings plus parity tests detect drift; fail-closed trades availability for
safety; pinned regeneration detects stale evidence. Success means byte-identical
evidence and six discoverable, evidence-linked, preliminary, telemetry-qualified
defaults. Fresh verification, not the inherited report, decides the final gate.
