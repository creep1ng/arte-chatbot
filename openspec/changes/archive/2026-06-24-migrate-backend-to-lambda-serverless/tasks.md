# Tasks: Migrate Backend to Lambda Serverless

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 1,200-2,000 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 state -> PR 2 runtime -> PR 3 infra -> PR 4 delivery |
| Delivery strategy | ask-on-risk / ask-always |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Lambda-safe state | PR 1 | Base = feature/tracker branch; repository, DynamoDB, tests. |
| 2 | Lambda runtime | PR 2 | Base = PR 1 branch; Mangum/config/package. |
| 3 | Serverless infra | PR 3 | Base = PR 2 branch; Lambda/API/DynamoDB/IAM/staging. |
| 4 | Delivery gates | PR 4 | Base = PR 3 branch; CI/CD, smoke, rollback. |

## Phase 1: State Foundation

- [x] 1.1 Create `backend/app/state_repository.py` with protocols/DTOs for sessions, ownership, tokens, rate windows, and buffer state.
- [x] 1.2 Add `backend/app/dynamodb_state_repository.py` with boto3, `PK/SK`, TTL, conditional owner writes, tokens, and rate counters.
- [x] 1.3 Modify `backend/app/config.py` for `STATE_BACKEND`, DynamoDB table/prefix/TTL, Lambda timeout, and secret references.
- [x] 1.4 Add tests in `backend/tests/test_state_repository.py`, `backend/tests/test_session.py`, and `backend/app/tests/test_message_buffer.py` for cold-start, ownership, buffer, and rate scenarios.

## Phase 2: Lambda Runtime and Package

- [x] 2.1 Modify `backend/main.py` to expose `handler = Mangum(app)` and keep local Uvicorn/Docker behavior.
- [x] 2.2 Modify `backend/app/session.py`, `backend/app/rate_limit.py`, and `backend/app/message_buffer.py` to use repositories, not background-task durability.
- [x] 2.3 Verify `backend/app/s3_client.py` and `backend/app/file_inputs.py` use default AWS credentials, Lambda-safe timeouts, and no static keys.
- [x] 2.4 Update `pyproject.toml` and package scripts for `mangum`, `uv` builds, and exclusion of `.env`, `.env.deploy`, credentials.
- [x] 2.5 Add tests for auth rejection and Mangum API Gateway events for `/health`, `/chat`, and `/buffer-result/{session_id}`.

## Phase 3: Serverless Infrastructure and Staging

- [x] 3.1 Create `infra/terraform/modules/lambda_backend/**` for Lambda, alias/version, IAM, logs, DynamoDB, HTTP API, permissions, and outputs.
- [x] 3.2 Wire `infra/terraform/envs/local-staging/**` to isolated names, direct endpoint, state, secret namespace, tags, and cleanup controls.
- [x] 3.3 Wire `infra/terraform/envs/prod/**` for Lambda/API Gateway HTTP API with no VPC/NAT.
- [x] 3.4 Add Terraform guard tests in `scripts/tests/test_terraform_foundation.py` and `scripts/tests/test_prod_terraform_wiring_checks.py` for isolation, IAM, credentials, and VPC absence.

## Phase 4: CI/CD, Verification, and Cutover

- [x] 4.1 Modify `.github/workflows/ci.yml` for lint/tests/package scan, staging deploy, smoke `/health` and `/chat`, and same-package promotion.
- [x] 4.2 Add or update smoke/evaluation scripts for S3 File Inputs, DynamoDB persistence, IAM-denied failures, and production URL isolation.
- [x] 4.3 Add rollback tasks/scripts to restore previous Lambda alias/version and prove target discovery.
- [x] 4.4 Add final-main merge prerequisite to revert the merge that introduced the existing deployment path before Lambda cutover lands on `main`.
- [x] 4.5 Update deployment docs/ADR notes for `.env.deploy`, staging endpoint, cutover reset policy, feature-branch-chain, and roadmap exclusions.

## Verification Fixes

- [x] Resolve `OPENAI_API_KEY_SECRET_REF` and `CHAT_API_KEY_SECRET_REF` from SSM Parameter Store or Secrets Manager at runtime when plaintext env vars are absent, with mocked auth/File Inputs/LLM/OpenAI tests.
- [x] Make multi-message buffer Lambda-safe by avoiding `asyncio.create_task` in repository-backed mode and letting `/buffer-result` durably flush due buffers from persisted state.
- [x] Fix `TestEndpointBufferIntegration` ownership setup so buffer tests expect `202` only for backend-issued/bound sessions.
- [x] Apply Ruff formatting to backend and relevant delivery scripts.
- [x] Align CI Lambda package Python with Terraform Lambda runtime and add workflow/Terraform/package guard tests.
- [x] Document Lambda variables/secrets, `.env.deploy` local/manual input semantics, and manual GitHub/AWS SSM/Secrets Manager setup for CD.

### Narrow Verify Retry Fixes

- [x] Reset LLM test settings/secret-ref cache and mock File Inputs settings with `OPENAI_API_KEY_SECRET_REF = None` when tests intentionally exercise missing/plaintext API-key paths.
- [x] Resolve `LLMClient` default model from current lazy settings at initialization time so tests and runtime respect refreshed configuration instead of import-time cache state.
- [x] Update the legacy Phase 4 deploy evidence guard to require the current `docker compose ... --wait --wait-timeout 120` command.

### Final Verification Blocker Fixes

- [x] Apply Ruff formatting to `scripts/tests/test_phase4_verification_checks.py` and verify script-inclusive Ruff check/format passes.
- [x] Make `backend/tests backend/app/tests` deterministic under pytest by disabling local `.env` loading, setting explicit test defaults, and resetting process-local backend state between tests.
- [x] Align legacy chat/tool tests with current serverless contracts for backend-issued session ownership and catalog-validated `raw/...` S3 datasheet paths.
- [x] Add event-loop-safe Mangum handler coverage and keep the expanded backend/app suite as the authoritative local safety gate: `CHAT_API_KEY=test-chat-key OPENAI_API_KEY=test-openai-key AWS_BUCKET_NAME=test-bucket uv run pytest backend/tests backend/app/tests`.

## Destructive Cutover Fixes

- [x] Remove production EC2 Compose, Cloudflare Tunnel, tunnel-secret SSM, VPC/subnet/tunnel variables, obsolete EC2/tunnel outputs, Cloudflare provider wiring, and SSM Run Command deploy-role references from `infra/terraform/envs/prod`.
- [x] Keep Lambda/API Gateway/DynamoDB/IAM/logs and ECR repositories needed by the remaining backend package and frontend/admin image delivery path.
- [x] Update production Terraform, workflow, and guard tests to expect Lambda-only cutover with no EC2 fallback requirement.
- [x] Update deployment docs and OpenSpec artifacts to state that EC2 fallback removal is destructive and production plan/apply no longer needs `TF_VAR_vpc_id`, `TF_VAR_public_subnet_id`, or `TF_VAR_edge_tunnel_secret`.

## Production Custom-Domain Cutover Fixes

- [x] Add API Gateway custom domain, ACM DNS validation, API mapping, and Cloudflare DNS records for `backend_hostname` without restoring Cloudflare Tunnel.
- [x] Apply production Terraform so `https://chatbot.artesolutions.com.co/health` returns healthy through the Lambda/API Gateway custom domain.
- [x] Document GitHub variable examples and clarify that Cloudflare zone/token are local Terraform DNS inputs, not Lambda runtime or GitHub promotion inputs.
- [x] Verify post-apply Terraform drift is clean and targeted Terraform guard tests pass.

## Post-Verification Cleanup Fixes

- [x] Ignore `.env.deploy` and align `.env.example` with Lambda secret refs, execution-role AWS access, DynamoDB state, and local `.env.deploy` semantics.
- [x] Clarify ADR-009 and deployment docs so Cloudflare DNS custom-domain management is distinct from retired Cloudflare Tunnel runtime.
- [x] Archive the superseded `low-cost-ec2-compose-exposure` OpenSpec change under `openspec/changes/archive/2026-06-22-low-cost-ec2-compose-exposure/`.
- [x] Retire or update active OpenSpec specs that described EC2/Fargate/Cloudflare Tunnel production as current source of truth.
- [x] Rework legacy Phase 4 verification checks so the active guard suite validates Lambda-only cleanup instead of retired EC2 Compose deploy evidence.
