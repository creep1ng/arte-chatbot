## Exploration: migrate-backend-to-lambda-serverless

### Current State

The backend currently runs as a containerized FastAPI app under Uvicorn. `backend/Dockerfile` installs dependencies with `uv`, copies `backend/` and `rag/`, exposes port `8000`, defines an HTTP healthcheck, and starts `uvicorn backend.main:app --host 0.0.0.0 --port 8000`.

Production infrastructure has already moved away from the older Fargate target toward low-cost EC2 Compose exposure. `infra/terraform/envs/prod/main.tf` creates ECR repositories, a Cloudflare Tunnel, SSM-stored tunnel token, a public-subnet EC2 Compose host, and optional GitHub OIDC deploy role. `infra/terraform/modules/ec2_compose_host/main.tf` provisions an EC2 instance with public IP, outbound-only security group, Docker, Compose, SSM managed-instance access, S3 read permissions, and runtime secret reads from SSM/Secrets Manager. The Compose template runs `backend`, `frontend`, `admin`, and `cloudflared`; `cloudflared` routes public hostnames to container DNS origins such as `http://backend:8000`.

Runtime configuration is environment-driven through Pydantic Settings in `backend/app/config.py`, with `.env` loading at import time in `backend/main.py`. `.env.example` documents local variables and explicitly says production should receive secrets from AWS Secrets Manager or SSM and use IAM roles/default credential chains. Current deployment resolves runtime secrets into `/opt/arte-chatbot/runtime.env` on the EC2 host during `deploy.sh` and passes them to Compose as an `env_file`.

The FastAPI app has `/health`, `/`, `/chat`, and `/buffer-result/{session_id}` endpoints. `/chat` authenticates with `CHAT_API_KEY`, applies a process-local rate limiter, binds session ownership, optionally buffers multi-message WhatsApp input, calls OpenAI with tool calling, downloads PDFs from S3, uploads File Inputs to OpenAI, and logs conversations to S3 when enabled.

Several production-relevant states are currently in memory:

| State | Current location | Serverless impact |
|-------|------------------|-------------------|
| Conversation history, user profile, token totals, session owner | `backend/app/session.py` global `SessionManager` dictionaries | Must move to DynamoDB or another durable store before horizontal/concurrent Lambda use. |
| Rate limiting | `backend/app/rate_limit.py` global in-memory sliding window | Must move to API Gateway throttling, DynamoDB, or another managed/shared limiter. |
| Multi-message buffer, debounce tasks, pending responses, processing flags | `backend/app/message_buffer.py` module-level dictionaries and `asyncio.create_task` | Not safe in Lambda because execution environments are ephemeral and background tasks can be frozen/terminated. |
| Module-level clients | `backend/main.py` creates `LLMClient`, `S3Client`, `FileInputsClient` at import | Can be reused across warm Lambda invocations, but secret/env validation must be safe at cold start and tests. |

### Affected Areas

- `backend/main.py` — add Lambda adapter entrypoint (`Mangum(app)` or equivalent), revisit import-time `.env` loading, module-level clients, background buffering callback, and HTTP timeout behavior.
- `backend/app/config.py` — add serverless deployment settings such as DynamoDB table names, secrets mode, allowed API hostnames, Lambda timeout-aware OpenAI timeouts, and optional `.env.deploy` parsing for deployment input only.
- `backend/app/session.py` — replace or abstract in-memory session storage behind a durable DynamoDB-backed repository.
- `backend/app/security.py` and `backend/app/rate_limit.py` — replace process-local rate limiting/session ownership checks with shared storage or API Gateway throttling plus DynamoDB session ownership.
- `backend/app/message_buffer.py` — redesign debounce/pending-response behavior for serverless; likely use DynamoDB TTL plus EventBridge/SQS/Step Functions, or disable buffering in initial Lambda cutover.
- `backend/app/s3_client.py` — already compatible with IAM role/default credential chain; IAM policy must allow only required bucket/object actions.
- `backend/app/file_inputs.py` and `backend/app/llm_client.py` — require outbound internet to OpenAI from Lambda; timeout/retry behavior must fit HTTP invocation limits.
- `.env.example` / deployment inputs — introduce `.env.deploy` as a local/manual deployment input source, not as a committed runtime secret file.
- `infra/terraform/**` — add or replace production backend infra with Lambda, API exposure, DynamoDB, IAM, CloudWatch logs, SSM/Secrets Manager references, packaging/build, and cutover outputs.
- `openspec/specs/*` — future proposal/spec should add serverless backend runtime requirements and supersede EC2 Compose backend exposure after cutover.

### Approaches

1. **Lambda without VPC + API Gateway HTTP API + DynamoDB** — Package the FastAPI backend for Lambda, expose it through HTTP API, persist state in DynamoDB, keep S3 datasheets in S3, store secrets in SSM/Secrets Manager, and call OpenAI through Lambda-managed public internet access.
   - Pros: lowest operational surface for a public HTTP API, avoids NAT Gateway fixed cost, keeps IAM-role access to S3/DynamoDB/secrets, gives API Gateway throttling/custom domain options, and fits the approved no-VPC direction.
   - Cons: requires application refactor for durable state, HTTP integrations have much shorter practical client timeouts than Lambda's 15-minute max, API Gateway adds service configuration and per-request cost.
   - Effort: High

2. **Lambda without VPC + Function URL + DynamoDB** — Expose the Lambda directly with a Function URL, keep the same no-VPC/DynamoDB/S3/secrets architecture, and put Cloudflare in front for DNS/proxying where needed.
   - Pros: simplest and potentially cheapest HTTP exposure; AWS positions Function URLs as the fastest path for direct Lambda HTTP endpoints.
   - Cons: fewer API-management controls than API Gateway: weaker native throttling, auth, request validation, custom-domain/API-stage features, and review/audit ergonomics. Current API-key auth would remain mostly in-app.
   - Effort: Medium-High

3. **Lambda in VPC + NAT Gateway** — Attach Lambda to private subnets and use NAT for OpenAI internet egress.
   - Pros: conventional private-subnet control model if future private resources are required.
   - Cons: contradicts the approved no-VPC low-cost target; AWS charges NAT Gateway for every provisioned hour plus data processing, so it creates a 24/7 fixed cost even for low traffic.
   - Effort: High

4. **Lambda in VPC + VPC endpoints only** — Use gateway endpoints for S3/DynamoDB and interface endpoints for supported AWS APIs.
   - Pros: gateway endpoints for S3 and DynamoDB have no hourly or data-processing charge and can reduce NAT traffic for AWS services.
   - Cons: insufficient for OpenAI because OpenAI is a public non-AWS internet destination; interface endpoints also add hourly/data-processing cost and do not replace generic internet egress.
   - Effort: High

### Recommendation

Proceed with Approach 1 as the default proposal target: **Lambda without VPC + API Gateway HTTP API + DynamoDB + S3 + SSM/Secrets Manager**, with OpenAI reached over Lambda's managed public internet path. Keep Function URL as an explicit decision point only if the next phase prioritizes minimal surface over API management.

This matches the approved decision: avoid NAT Gateway, avoid managed deployment credentials in code, and accept moving application state to DynamoDB. It also gives a cleaner production API boundary than Function URLs for throttling, future custom domain mapping, logs/metrics, and Cloudflare integration.

Use Terraform as the recommended infrastructure path because the repository already has Terraform modules, test scripts around Terraform wiring, and production IaC conventions. SAM or CDK would be viable for Lambda packaging speed, but mixing IaC systems would increase project cognitive load unless Terraform packaging becomes a blocker.

### Network and Cost Comparison

| Option | Internet path to OpenAI | AWS service access | Cost/ops summary |
|--------|--------------------------|--------------------|------------------|
| No VPC Lambda | Lambda-managed public internet | IAM calls to S3, DynamoDB, SSM/Secrets Manager through AWS public endpoints | Best fit here: no NAT Gateway, no subnet/ENI management, pay mostly per Lambda/API/DynamoDB usage. |
| VPC + NAT Gateway | Private subnet routes `0.0.0.0/0` through NAT | S3/DynamoDB can still use endpoints | NAT Gateway is charged while provisioned and available plus per-GB processing; wasteful for low-traffic chatbot. |
| VPC + endpoints only | No generic internet path unless NAT/egress added | S3/DynamoDB gateway endpoints are free of hourly/data-processing charges; interface endpoints cost extra | Cannot reach OpenAI with only S3/DynamoDB endpoints, so not sufficient for this backend. |

Important verified constraints:

- A single Lambda invocation can run up to **900 seconds / 15 minutes**. Durable workflow products can orchestrate longer processes, but they do not remove the per-invocation Lambda limit.
- API Gateway HTTP/REST integration timeouts are much shorter than 15 minutes by default/common quota, so synchronous `/chat` must be designed for fast responses or moved to async polling/webhook semantics.

### Application Changes Needed

- Add `mangum` dependency and expose a Lambda handler while preserving the existing FastAPI app for local tests and Docker until cutover.
- Split runtime `.env` behavior: `.env` remains local development; `.env.deploy` may feed manual/controlled deployment scripts but must not be committed or loaded as Lambda runtime secret source.
- Move session history, session ownership, user profile, and token totals to DynamoDB with TTL and conditional writes for ownership/concurrency safety.
- Replace in-memory rate limiting with API Gateway throttling and/or DynamoDB-backed counters; avoid relying on Lambda warm-container memory.
- Redesign multi-message buffer. Initial safe path is disabling it for Lambda cutover or converting it to DynamoDB + delayed event/queue + polling. `asyncio.create_task` debounce is not a Lambda-safe durability boundary.
- Tune OpenAI/S3 timeouts below HTTP exposure limits; consider async job pattern for slow File Inputs flows.
- Preserve structured logs with request/session IDs in CloudWatch; consider X-Ray or OpenTelemetry later, but do not block first migration on a full observability platform.

### Infrastructure Changes Needed

- Add Terraform-managed Lambda function/package, IAM execution role, CloudWatch log group, API Gateway HTTP API or Function URL, DynamoDB table(s), SSM/Secrets Manager references, Lambda permissions, and outputs for public URL/domain cutover.
- IAM minimum scope: S3 read for catalog/datasheets and optional write for conversation logs, DynamoDB CRUD only for the state table/indexes required, `ssm:GetParameter`/`secretsmanager:GetSecretValue` only for named secrets, CloudWatch Logs for Lambda, no broad AWS credentials in environment.
- Packaging should use reproducible `uv` export/sync/build steps and avoid bundling local `.env` or credentials. If Lambda zip size becomes painful due to dependencies, evaluate Lambda container image while still running Lambda without VPC.
- Deployment should be manual/controlled or role-based: use local operator AWS profile/SSO or GitHub OIDC role where approved, never hardcoded AWS keys. `.env.deploy` should act as input names/ARNs/flags, not secret storage.

### Open Questions and Risks

- Function URL vs API Gateway HTTP API: API Gateway is recommended, but the cost/control tradeoff should be accepted explicitly in proposal.
- Synchronous `/chat` viability: OpenAI File Inputs plus S3 download may exceed HTTP timeout budgets under load or large PDFs.
- Durable execution: Step Functions/Lambda Durable Execution style workflows can support longer overall flows, but individual Lambda invocations still cap at 15 minutes and HTTP clients still time out.
- Secrets strategy: choose SSM Parameter Store vs Secrets Manager per secret rotation needs and cost; both must avoid Terraform state leakage of secret values.
- Domain/Cloudflare cutover: decide whether Cloudflare proxies API Gateway custom domain, Function URL, or direct AWS-managed URL during first release.
- Conversation migration: current in-memory sessions cannot be migrated after process stop; if EC2 has live conversations, cutover should announce/reset sessions or build a temporary export before shutdown.
- Observability: CloudWatch logs are baseline; need alarms for Lambda errors/throttles/duration, API 5xx/4xx, DynamoDB throttles, and OpenAI failures.
- Line budget: likely exceeds 400 changed lines because app state, infra, tests, and deployment docs all change. Plan chained PRs.

### Migration Plan

1. **Design/proposal** — define the serverless capability, endpoint choice, state model, timeout semantics, and cutover constraints.
2. **State abstraction** — introduce repository interfaces and DynamoDB implementation for sessions/ownership/profile/token totals while keeping local/in-memory tests viable.
3. **Lambda entrypoint** — add Mangum handler, dependency/package updates, cold-start-safe config, and local tests for API Gateway event handling.
4. **Serverless infrastructure** — add Terraform for DynamoDB, Lambda, API Gateway/Function URL, IAM, logs, parameters/secrets references, and deployment outputs.
5. **Buffer/rate-limit decision** — disable or reimplement buffer for Lambda; move rate limiting to shared/API-layer enforcement.
6. **Staging validation** — deploy a separate serverless backend URL, run health/chat/file-input smoke tests, latency checks, and IAM negative checks.
7. **Cloudflare/domain cutover** — route backend hostname to the serverless endpoint, keep EC2 Compose rollback path temporarily, then remove backend from Compose after soak.
8. **Cleanup** — archive old backend EC2/ECR/deploy assumptions once Lambda is verified; keep frontend/admin decisions separate unless intentionally migrated later.

### Ready for Proposal

Yes — proceed to proposal for `migrate-backend-to-lambda-serverless`, scoped to backend migration only. The proposal should warn that this is almost certainly a chained change over the 400-line review budget: PR 1 state abstraction, PR 2 Lambda handler/config, PR 3 infrastructure, PR 4 cutover/cleanup.
