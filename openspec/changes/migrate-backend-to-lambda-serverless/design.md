# Design: Migrate Backend to Lambda Serverless

Move only the backend runtime from EC2 Compose to Lambda. Keep the FastAPI product surface (`/health`, `/chat`, `/buffer-result/{session_id}`), S3 File Inputs flow, tool calling, API-key auth, and conversation logging semantics. Serverless-safety work is limited to Lambda handler/config, DynamoDB state, shared rate counters, packaging, Terraform, staging, CI/CD, rollout, and rollback.

## Technical Approach

Add a Lambda adapter around the existing FastAPI `app` and preserve local Uvicorn/Docker execution during rollout. Replace Lambda-unsafe globals in `backend/app/session.py`, `backend/app/rate_limit.py`, and `backend/app/message_buffer.py` with repository-backed behavior where required for current functionality. Keep Lambda outside VPC so OpenAI is reached through Lambda-managed public internet and AWS services are reached through IAM-authorized clients.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| HTTP boundary | API Gateway HTTP API -> Lambda/Mangum | Function URL | HTTP API gives stages, throttling hooks, access logs, custom-domain/cutover ergonomics while still staying low ops. |
| Network | Lambda without VPC/NAT | VPC + NAT/endpoints | OpenAI requires public egress; NAT adds fixed cost and violates target. |
| State | Single DynamoDB state table with typed items and TTL | Redis, RDS, in-memory | DynamoDB is serverless, cheap for intermittent traffic, supports conditional ownership writes. |
| Multi-message buffer | Persist request/polling state in DynamoDB; no `asyncio.create_task` as durability boundary | SQS/EventBridge/Step Functions now | Current phase preserves behavior safely; workflow services remain roadmap. |
| Secrets | Lambda env contains non-sensitive config and secret references or injected resolved values from SSM/Secrets Manager | `.env.deploy` runtime file, static AWS keys | Matches current SSM/Secrets pattern and avoids committed/local secret files. |

## Data Flow

```text
Client/Cloudflare -> API Gateway HTTP API -> Lambda handler -> FastAPI app
  -> auth/rate check -> DynamoDB state repository
  -> S3 catalog/PDF -> OpenAI Files + tool calls -> response
  -> DynamoDB session update + optional S3 conversation log
```

`/buffer-result/{session_id}` reads pending buffered results from DynamoDB so polling works across cold starts.

## File Changes

| File | Action | Description |
|---|---|---|
| `backend/main.py` | Modify | Add `handler = Mangum(app)`, remove Lambda runtime dependency on `.env.deploy`, inject state/rate/buffer repositories. |
| `backend/app/config.py` | Modify | Add `state_backend`, DynamoDB table/prefix/TTL, Lambda timeout-aware settings, secret reference names. |
| `backend/app/state_repository.py` | Create | Protocols and DTOs for session, owner, profile, token totals, rate counters, buffer state. |
| `backend/app/dynamodb_state_repository.py` | Create | boto3 DynamoDB implementation with conditional writes and TTL. |
| `backend/app/session.py` | Modify | Keep in-memory implementation for tests/local; delegate through repository interface. |
| `backend/app/rate_limit.py` | Modify | Add DynamoDB-backed shared limiter contract; preserve endpoint response behavior. |
| `backend/app/message_buffer.py` | Modify | Store buffered messages/pending responses/processing flags durably; avoid background-task-only semantics. |
| `backend/app/s3_client.py`, `backend/app/file_inputs.py` | Modify | Verify role/default credential and timeout behavior; no static credentials required. |
| `pyproject.toml` | Modify | Add `mangum`; keep `uv` workflow. |
| `infra/terraform/modules/lambda_backend/**` | Create | Lambda, IAM, log group, API Gateway HTTP API, aliases, permissions, DynamoDB. |
| `infra/terraform/envs/prod/**` | Modify | Wire Lambda/API Gateway/DynamoDB as the only production backend and remove EC2 Compose/Cloudflare Tunnel inputs, modules, and outputs. |
| `.github/workflows/ci.yml` | Modify | Add Lambda package, staging deploy, smoke/evaluation, promote same package, rollback. |

## Interfaces / Contracts

```python
handler = Mangum(app)

class ChatbotStateRepository(Protocol):
    def get_session(self, session_id: str) -> SessionState: ...
    def append_turn(self, session_id: str, turn: ChatTurn) -> None: ...
    def bind_owner(self, session_id: str, owner: str) -> None: ...  # conditional if absent
    def add_token_usage(self, session_id: str, totals: TokenTotals) -> None: ...
    def check_rate_limit(self, principal: str, limit: int, window_seconds: int) -> RateLimitDecision: ...
    def append_buffer_message(self, session_id: str, message: str) -> BufferState: ...
    def set_pending_response(self, session_id: str, response_json: str) -> None: ...
```

DynamoDB keys: `PK=SESSION#{session_id}` with `SK` values `META`, `TURN#{iso_timestamp}`, `TOKENS`, `BUFFER`; `PK=RATE#{principal}`, `SK=WINDOW#{epoch_bucket}` for counters. Items include `expires_at` TTL, `owner`, `profile`, `source_documents`, and token totals. Ownership writes use `attribute_not_exists(owner) OR owner = :owner`.

## Staging Design

Use isolated names/prefixes: Lambda alias/function, HTTP API stage/direct URL, DynamoDB table or prefixed keys, log group, and SSM/Secrets namespace. Staging validates `/health`, authenticated `/chat`, S3 PDF/File Inputs, DynamoDB persistence, and IAM-denied negative cases without touching production routes.

## CI/CD Design

PR: lint, tests, package zip, artifact secret-file scan. Main/manual: assume approved OIDC/manual role, deploy staging package, run smoke/evaluation, publish immutable Lambda version, promote alias to production, verify health/chat, retain previous alias target for rollback. No hardcoded AWS deploy credentials.

## Migration / Rollout and Rollback

Use a feature-branch-chain for review. Deploy Lambda in parallel, run staging, then production shadow/smoke. The final production Terraform root is Lambda-only after an approved destructive cutover: EC2 Compose, Cloudflare Tunnel, VPC/subnet inputs, tunnel secret inputs, obsolete outputs, and SSM Run Command deploy permissions are removed before final apply. Rollback moves alias/API mapping to the prior Lambda version only. No live EC2 sessions exist, so no session export/drain is required.

## Future Evolution Roadmap

Non-blocking only: API Gateway/WAF/DynamoDB precision limiter, SQS/EventBridge/Step Functions for durable buffering/workflows, async chat jobs with polling/webhooks for slow File Inputs, alarms/dashboards/X-Ray/OTel.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | state repository, ownership, limiter, buffer, config | pytest with fake/DynamoDB-local style mocks |
| Integration | Lambda event -> FastAPI, S3/File Inputs path, IAM failures | Mangum/API Gateway event tests plus staging smoke |
| E2E | direct staging `/health` and `/chat`, evaluation harness, rollback | CI workflow gates against staging URL |

## Open Questions

- [x] Production will use API Gateway HTTP API over Function URL.
- [x] No live EC2 sessions exist currently; cutover does not require session export/drain.
