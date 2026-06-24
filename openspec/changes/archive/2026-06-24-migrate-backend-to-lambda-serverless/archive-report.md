# Archive Report: Migrate Backend to Lambda Serverless

## Outcome

The Lambda serverless migration is archived. The active OpenSpec deltas were synced into the main specifications and the change folder was moved to `openspec/changes/archive/2026-06-24-migrate-backend-to-lambda-serverless/`.

## Traceability

| Artifact | Path |
|---|---|
| Proposal | `openspec/changes/archive/2026-06-24-migrate-backend-to-lambda-serverless/proposal.md` |
| Design | `openspec/changes/archive/2026-06-24-migrate-backend-to-lambda-serverless/design.md` |
| Tasks | `openspec/changes/archive/2026-06-24-migrate-backend-to-lambda-serverless/tasks.md` |
| Verification report | `openspec/changes/archive/2026-06-24-migrate-backend-to-lambda-serverless/verify-report.md` |
| Delta specs | `openspec/changes/archive/2026-06-24-migrate-backend-to-lambda-serverless/specs/` |

## PR #224 Notes

The source-of-truth specs now explicitly cover the Lambda PR preview behavior requested after PR #224:

- Ephemeral pull-request preview stack under the `infra/terraform/envs/pr-preview` contract.
- Same-repository PR gating, fork safety, and pull-request cleanup behavior.
- Runtime secret ARN JSON and KMS ARN JSON sourced from GitHub Secrets, not Variables.
- Preview smoke/evaluation checks resolving `CHAT_API_KEY` from runtime secret ARN JSON.
- Deterministic File Inputs smoke prompt using the smaller LONGi PDF to reduce Lambda timeout risk.
- Preview DynamoDB persistence verification and deploy-role `Query`/`GetItem` read permissions.
- Direct File Input response behavior after `leer_ficha_tecnica` when the File Input answer is sufficient, avoiding redundant final LLM calls that can exceed Lambda timeouts.

## Specs Synced

| Spec | Action | Notes |
|---|---|---|
| `openspec/specs/serverless-chatbot-backend/spec.md` | Updated | Added PR preview, preview smoke/persistence, and direct File Input response requirements. |
| `openspec/specs/local-staging-isolation/spec.md` | Updated | Added PR preview isolation/cleanup requirements and normalized requirement text for strict validation. |
| `openspec/specs/ecs-runtime-configuration/spec.md` | Updated | Added GitHub Secrets-only runtime JSON requirement and deploy-role DynamoDB read-permission scenarios. |
| `openspec/specs/ecr-cd-promotion/spec.md` | Updated | Added same-repo PR preview gating, cleanup, and preview smoke state-read permission scenarios. |

## Verification

| Command | Result |
|---|---|
| `openspec validate --strict` | Informational: no target selected; CLI suggested `--all`, `--changes`, or `--specs`. |
| `openspec validate --specs` | PASS: 5 specs passed, 0 failed. |
| `git diff --check` | PASS: no whitespace errors. |
| Directory inspection | PASS: active change folder is absent and archive folder contains proposal, design, tasks, verify report, apply progress, exploration, and specs. |

## Warnings

- This archive pass did not run external services or cloud-mutating workflows.
- The current worktree contains pre-existing dirty files `.kilo/package-lock.json` and `.kilocode/package-lock.json`; they were not touched by this archive work.
- Local inspection found `infra/terraform/envs/pr-preview` absent in this checkout even though the specs now capture the requested PR-preview contract; no infrastructure files were changed in archive mode.

## Skill Resolution

`paths-injected`: the requested skill paths were loaded through the skill loader because direct filesystem reads of global skill files were blocked by the external-directory policy. No delegation or sub-agents were used.
