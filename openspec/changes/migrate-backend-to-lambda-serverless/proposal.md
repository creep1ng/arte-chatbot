# Proposal: Migrate Backend to Lambda Serverless

## Intent

Move the existing chatbot backend from EC2 Compose/Cloudflare Tunnel to a low-cost AWS Lambda runtime. The driver is cost and operational simplicity: the backend should not need always-on EC2/Fargate capacity or NAT Gateway just to serve intermittent chatbot traffic and call OpenAI.

## Scope

### In Scope
- Migrate the existing FastAPI chatbot backend functionality to Lambda **without VPC**.
- Use API Gateway HTTP API as the default public boundary, with direct staging endpoint support.
- Move Lambda-unsafe application state to DynamoDB: conversation/session state, ownership, profile, token totals, and any required shared counters.
- Keep S3 datasheets, File Inputs, tool calling, chatbot authentication, health checks, and conversation logging behavior functionally equivalent.
- Store secrets/config through IAM roles plus SSM Parameter Store or Secrets Manager; no hardcoded deploy credentials.

### Out of Scope
- Replacing the whole chatbot workflow with SQS/EventBridge/Step Functions.
- Full WAF/rate-limit redesign beyond what is required for safe Lambda operation.
- Migrating frontend/admin hosting or unrelated infrastructure.
- VPC/NAT Gateway/Fargate/EC2 backend alternatives.

## Capabilities

### New Capabilities
- `serverless-chatbot-backend`: Lambda runtime, API exposure, durable state, staging, CI/CD, rollback, and production cutover requirements.

### Modified Capabilities
- `ecs-runtime-configuration`: Supersede backend runtime secret/config requirements for Lambda while preserving no-static-key behavior.
- `ecr-cd-promotion`: Extend deployment gating from container/ECS promotion to Lambda package promotion.
- `local-staging-isolation`: Extend isolated staging requirements to serverless staging resources and direct chatbot endpoint validation.

## Approach

Target architecture: Cloudflare or direct client -> API Gateway HTTP API -> Lambda FastAPI adapter -> DynamoDB/S3/SSM/Secrets Manager/OpenAI over Lambda-managed public internet. Terraform remains the preferred IaC path.

Migration phases: (1) state abstraction, (2) DynamoDB-backed state, (3) Lambda handler/package/config, (4) Terraform serverless resources, (5) staging validation, (6) Lambda/API Gateway production cutover, (7) destructive EC2 Compose/Cloudflare Tunnel cleanup before final apply.

## Staging

Create fast, isolated staging with separate Lambda alias/function, API Gateway stage or direct invoke URL, DynamoDB table/prefix, secret/config namespace, log group, and short TTL tags. Use non-production data/config where possible; allow read-only catalog access if explicitly approved. Validate `/health`, authenticated `/chat`, S3 PDF/File Inputs path, DynamoDB state persistence, logs, and IAM-denied negative cases. Teardown destroys staging resources and expires DynamoDB items.

## CI/CD

Build/package with reproducible `uv` steps, excluding `.env` and credentials. PRs run lint/tests/package checks. Main or approved workflow deploys staging through OIDC/manual role, runs smoke/evaluation, then promotes the same package to production. Cutover uses Lambda/API Gateway as the only production backend. Rollback restores the previous Lambda version/alias; EC2 Compose/Cloudflare Tunnel fallback was intentionally removed and is not available after this destructive cutover.

## Future Evolution Roadmap

| Current capability | Future replacement | Reason | Adoption condition |
|---|---|---|---|
| In-app rate limiting | API Gateway throttling/WAF plus DynamoDB limiter if per-session precision is needed | Shared enforcement and abuse protection | Traffic/abuse requires controls beyond basic API key |
| In-process message buffer/debounce | SQS + EventBridge Scheduler or Step Functions | Lambda cannot rely on background tasks | Multi-message buffering must be durable |
| Synchronous slow chat calls | Async job + polling/webhook | API Gateway timeout pressure | File Inputs latency exceeds HTTP budget |
| Basic CloudWatch logs | Alarms, dashboards, X-Ray/OTel | Operational visibility | Production error/latency SLOs are defined |

These are roadmap items only; current scope is functional Lambda migration.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `backend/` | Modified | Lambda adapter, config, state, rate/session behavior |
| `rag/` | Modified | Preserve File Inputs behavior under Lambda packaging |
| `infra/terraform/**` | Modified | Lambda/API Gateway/DynamoDB/IAM/logs/secrets/staging |
| `.github/workflows/**` | Modified | Package, deploy, smoke/evaluation, rollback gates |
| `openspec/specs/**` | Modified/New | Serverless backend specs and deltas |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Chat latency exceeds API timeout | Med | Timeout tuning; future async roadmap |
| In-memory behavior changes during state migration | High | Repository abstraction, tests, staged soak |
| Secrets leak into package/state | Med | IAM/OIDC, SSM/Secrets Manager refs, artifact checks |
| Cutover disrupts live sessions | Med | Accept reset or add explicit drain/export plan |

## Rollback Plan

Roll back by moving the production Lambda alias/API mapping to the previous Lambda version. Preserve previous package, DynamoDB table backups/PITR where enabled, and deployment outputs. EC2 Compose/Cloudflare Tunnel rollback is out of scope after the approved destructive cutover because the existing EC2 deployment had no real data.

## Dependencies

- Approved AWS IAM role/OIDC or manual operator credentials.
- Existing S3 catalog/datasheet bucket and OpenAI/CHAT secrets in SSM or Secrets Manager.
- Terraform state strategy for staging and production.

## Open Questions

- Confirm API Gateway HTTP API over Function URL for production.
- Decide whether current multi-message buffer is disabled at cutover or minimally reimplemented.
- Decide live-session reset/drain policy.

## Review Forecast

Expected to exceed 400 changed lines. Use chained PRs: state abstraction, Lambda package/config, Terraform staging/prod, CI/CD + cutover cleanup.

## Success Criteria

- [ ] Lambda staging serves `/health` and authenticated `/chat` through direct endpoint.
- [ ] Chatbot preserves current S3 File Inputs/tool-calling behavior.
- [ ] State required for concurrent Lambda use is durable in DynamoDB.
- [ ] CI/CD gates package, staging smoke/evaluation, production promotion, and rollback.
- [ ] Production cutover avoids VPC, NAT Gateway, hardcoded credentials, and backend EC2 dependency.
