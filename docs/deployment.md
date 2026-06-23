# Lambda Serverless Deployment Guide

Production cutover moves the backend from EC2 Compose/Cloudflare Tunnel to AWS Lambda behind API Gateway HTTP API. The production Terraform root is now Lambda-only: the EC2 Compose host, Cloudflare Tunnel, and SSM Run Command deploy path were intentionally removed as a destructive cutover. Frontend and admin image delivery stay on the existing ECR path.

## Current production status

| Area | Status |
|---|---|
| Backend target | Lambda + API Gateway HTTP API is the cutover target. |
| Existing path | EC2 Compose/Cloudflare Tunnel production fallback has been removed. |
| Staging | Lambda staging deploys the same scanned package artifact to a non-production direct endpoint. |
| Production Terraform inputs | `TF_VAR_vpc_id`, `TF_VAR_public_subnet_id`, `TF_VAR_cloudflare_account_id`, and `TF_VAR_edge_tunnel_secret` are no longer required. `TF_VAR_cloudflare_zone_id` plus `CLOUDFLARE_API_TOKEN` are used only to manage the backend custom-domain DNS record. |
| Backend custom domain | `https://chatbot.artesolutions.com.co` is expected to work only after Terraform creates the API Gateway custom domain, ACM DNS validation record, API mapping, and Cloudflare CNAME. The direct `execute-api` URL may work before this. |
| Session reset policy | No live EC2 sessions exist; cutover may reset in-memory sessions. Durable Lambda state starts in DynamoDB. |

## Quick path

1. Open the fourth feature-branch-chain PR for delivery gates only.
2. Let CI lint, run targeted tests, build `dist/lambda/backend.zip`, and scan the package for `.env`, `.env.deploy`, and plaintext credentials.
3. Deploy Lambda staging from the scanned artifact and smoke the direct staging endpoint.
4. Run staging `/health`, authenticated `/chat`, S3 File Inputs, DynamoDB persistence, IAM-denied negative probe, and production URL isolation checks.
5. Plan/apply `infra/terraform/envs/prod` with Lambda-only inputs; do not provide VPC, public subnet, Cloudflare account, or tunnel secret variables. Provide Cloudflare zone/token only for DNS custom-domain management.
6. Enable Lambda cutover variables and promote the same package hash to the production Lambda alias.
7. If production verification fails, restore the previous Lambda alias version with `scripts/lambda_rollback.py`.

## Deployment configuration matrix

There are three different places for configuration. Keep them separate:

1. **GitHub** drives CI/CD jobs and smoke checks.
2. **AWS SSM/Secrets Manager** stores Lambda runtime secret values.
3. **`.env.deploy`** is local-only input for operator-run Terraform.

### GitHub Repository Variables

GitHub Variables are non-sensitive values used by `.github/workflows/ci.yml`.

| Name | Kind | Example | Meaning |
|---|---|---|---|
| `AWS_REGION` | GitHub Variable | `us-east-2` | Region used by workflow AWS actions. Defaults to `us-east-2` if absent. |
| `BACKEND_ECR_REPOSITORY_URL` | GitHub Variable | `521170872319.dkr.ecr.us-east-2.amazonaws.com/arte-chatbot-prod-backend` | Backend ECR repository used by image publishing jobs. |
| `FRONTEND_ECR_REPOSITORY_URL` | GitHub Variable | `521170872319.dkr.ecr.us-east-2.amazonaws.com/arte-chatbot-prod-frontend` | Frontend ECR repository used by image publishing jobs. |
| `ADMIN_ECR_REPOSITORY_URL` | GitHub Variable | `521170872319.dkr.ecr.us-east-2.amazonaws.com/arte-chatbot-prod-admin` | Admin ECR repository used by image publishing jobs. |
| `LAMBDA_CUTOVER_ENABLED` | GitHub Variable | `true` | Enables production Lambda promotion jobs on `main`. Keep `false` or unset to disable production promotion. |
| `LAMBDA_PROD_FUNCTION_NAME` | GitHub Variable | `arte-chatbot-prod-backend-lambda` | Production Lambda function to update during promotion. |
| `LAMBDA_PROD_ALIAS_NAME` | GitHub Variable | `live` | Production Lambda alias that receives traffic. |
| `LAMBDA_PROD_API_URL` | GitHub Variable | `https://chatbot.artesolutions.com.co` | Production API URL used by production smoke checks. |
| `LAMBDA_PROD_STATE_TABLE_NAME` | GitHub Variable | `arte-chatbot-prod-backend-lambda-state` | DynamoDB table checked by production smoke. |
| `LAMBDA_PROD_STATE_KEY_PREFIX` | GitHub Variable | `prod` | DynamoDB state prefix checked by production smoke. |
| `LAMBDA_STAGING_FUNCTION_NAME` | GitHub Variable | `<staging-lambda-function-name>` | Staging Lambda function updated before production promotion. Required when `LAMBDA_CUTOVER_ENABLED=true` on `main`. |
| `LAMBDA_STAGING_ALIAS_NAME` | GitHub Variable | `staging` | Staging alias. Defaults to `staging` in workflow expressions. |
| `LAMBDA_STAGING_API_URL` | GitHub Variable | `https://<api-id>.execute-api.us-east-2.amazonaws.com/` | Direct staging endpoint for smoke/evaluation. |
| `LAMBDA_STAGING_STATE_TABLE_NAME` | GitHub Variable | `<staging-state-table-name>` | DynamoDB table checked by staging smoke. |
| `LAMBDA_STAGING_STATE_KEY_PREFIX` | GitHub Variable | `<staging-prefix>` | DynamoDB state prefix checked by staging smoke. |
| `LAMBDA_STAGING_IAM_DENIED_DYNAMODB_TABLE_NAME` | GitHub Variable | `<denied-table-name>` | Resource expected to fail the IAM-denied staging probe. |
| `LAMBDA_STAGING_SMOKE_CHAT_MESSAGE` | GitHub Variable | `Validación staging: ...` | Optional staging smoke prompt. |

`PROD_BACKEND_RUNTIME_ENV_JSON` is **not used by the current workflow**. Runtime environment values are applied by Terraform through `.env.deploy`, not by GitHub promotion jobs. Chatwoot runtime settings follow the same rule: set them through Terraform inputs, not GitHub Actions variables.

### GitHub Repository Secrets

GitHub Secrets are sensitive values used by workflow jobs. They are not read by Lambda at runtime unless a workflow explicitly injects them into a command.

| Name | Kind | Example | Meaning |
|---|---|---|---|
| `AWS_CI_ROLE_ARN` | GitHub Secret | `arn:aws:iam::521170872319:role/<ci-role>` | OIDC role used by CI jobs that need AWS access. |
| `AWS_DEPLOY_ROLE_ARN` | GitHub Secret | `arn:aws:iam::521170872319:role/<deploy-role>` | OIDC role used by staging/prod Lambda deploy jobs. |
| `OPENAI_API_KEY` | GitHub Secret | `<openai-api-key>` | CI/evaluation plaintext credential. Lambda production runtime should use AWS SSM/Secrets Manager instead. |
| `CHAT_API_KEY` | GitHub Secret | `<chat-api-key>` | Plaintext API key used by production smoke checks. Do not put the Secrets Manager ARN here. |
| `AWS_BUCKET_NAME` | GitHub Secret | `arte-chatbot-fichas-tecnicas` | S3 bucket used by CI/evaluation jobs. |
| `PROD_BACKEND_HOSTNAME` | GitHub Secret | `chatbot.artesolutions.com.co` | Masked production hostname used only as a forbidden URL during staging isolation checks. |
| `LAMBDA_STAGING_CHAT_API_KEY` | GitHub Secret | `<staging-chat-api-key>` | Plaintext staging `/chat` API key for staging smoke. Required when `LAMBDA_CUTOVER_ENABLED=true` on `main`. |

`PROD_BACKEND_RUNTIME_SECRET_ARNS_JSON` is **not used by the current workflow**. Runtime secret ARNs are Terraform inputs in `.env.deploy`. Keep this secret only if another operator workflow consumes it later.

### GitHub Actions deploy inputs

These are the inputs the deploy jobs read from GitHub. They deploy and smoke the already-configured Lambda function; they do not create Chatwoot runtime configuration.

| Workflow job | GitHub Variables | GitHub Secrets | Notes |
|---|---|---|---|
| `deploy-lambda-staging` | `LAMBDA_STAGING_FUNCTION_NAME`, `LAMBDA_STAGING_ALIAS_NAME`, `LAMBDA_STAGING_API_URL`, `LAMBDA_STAGING_STATE_TABLE_NAME`, `LAMBDA_STAGING_STATE_KEY_PREFIX`, `LAMBDA_STAGING_IAM_DENIED_DYNAMODB_TABLE_NAME` | `AWS_DEPLOY_ROLE_ARN`, `LAMBDA_STAGING_CHAT_API_KEY` | Publishes the package and moves the staging alias. |
| `smoke-lambda-staging` | `LAMBDA_STAGING_IAM_DENIED_DYNAMODB_TABLE_NAME`, `LAMBDA_PROD_API_URL`, `LAMBDA_STAGING_SMOKE_CHAT_MESSAGE` | `AWS_DEPLOY_ROLE_ARN`, `LAMBDA_STAGING_CHAT_API_KEY`, `PROD_BACKEND_HOSTNAME` | Uses deploy job outputs for staging API/table/prefix. |
| `promote-lambda-production` | `LAMBDA_PROD_FUNCTION_NAME`, `LAMBDA_PROD_ALIAS_NAME`, `LAMBDA_PROD_API_URL`, `LAMBDA_PROD_STATE_TABLE_NAME`, `LAMBDA_PROD_STATE_KEY_PREFIX` | `AWS_DEPLOY_ROLE_ARN`, `CHAT_API_KEY` | Publishes the same artifact to the production alias. |
| `verify-lambda-production` | Uses production outputs from `promote-lambda-production` | `AWS_DEPLOY_ROLE_ARN`, `CHAT_API_KEY` | Runs production `/health` and `/chat` smoke checks. |
| `rollback-lambda-production` | `LAMBDA_PROD_FUNCTION_NAME`, `LAMBDA_PROD_ALIAS_NAME` | `AWS_DEPLOY_ROLE_ARN` | Uses `workflow_dispatch.rollback_target_version` or the previous version captured by promotion. |

Do not add Chatwoot AgentBot tokens or webhook secrets to GitHub Actions for Lambda runtime. Those values belong in AWS SSM Parameter Store or Secrets Manager and are exposed to Lambda only as `*_SECRET_REF` ARNs created by Terraform.

### AWS SSM Parameter Store / Secrets Manager

Lambda runtime secrets live in AWS, not in GitHub. Terraform passes only ARNs into Lambda as `*_SECRET_REF` environment variables, and the Lambda execution role reads the secret values at runtime.

| Name | Kind | Example | Meaning |
|---|---|---|---|
| `/arte-chatbot/prod/openai-api-key` | SSM SecureString or Secrets Manager secret | `sk-proj-...` | Production OpenAI key read by Lambda as `OPENAI_API_KEY`. |
| `/arte-chatbot-prod/prod/runtime/CHAT_API_KEY` | Secrets Manager secret | `<chat-api-key>` | Production `/chat` API key read by Lambda as `CHAT_API_KEY`. |
| `/arte-chatbot-prod/prod/runtime/CHATWOOT_AGENT_BOT_TOKEN` | SSM SecureString or Secrets Manager secret | `<chatwoot-agent-bot-token>` | Chatwoot AgentBot API token read by Lambda as `CHATWOOT_AGENT_BOT_TOKEN`. |
| `/arte-chatbot-prod/prod/runtime/CHATWOOT_WEBHOOK_SECRET` | SSM SecureString or Secrets Manager secret | `<chatwoot-webhook-hmac-secret>` | HMAC secret used to verify `/webhook/chatwoot` signatures. |

For new Chatwoot production rollout, create the SSM SecureString parameters before applying Terraform:

```bash
read -r -s CHATWOOT_AGENT_BOT_TOKEN
aws ssm put-parameter \
  --name "/arte-chatbot-prod/prod/runtime/CHATWOOT_AGENT_BOT_TOKEN" \
  --type SecureString \
  --value "$CHATWOOT_AGENT_BOT_TOKEN" \
  --overwrite

read -r -s CHATWOOT_WEBHOOK_SECRET
aws ssm put-parameter \
  --name "/arte-chatbot-prod/prod/runtime/CHATWOOT_WEBHOOK_SECRET" \
  --type SecureString \
  --value "$CHATWOOT_WEBHOOK_SECRET" \
  --overwrite
```

The Lambda environment variable names are generated by Terraform from `backend_runtime_secret_arns`:

| Lambda env name | Kind | Example | Meaning |
|---|---|---|---|
| `OPENAI_API_KEY_SECRET_REF` | Lambda env var containing ARN | `arn:aws:ssm:us-east-2:521170872319:parameter/arte-chatbot/prod/openai-api-key` | Points Lambda to the OpenAI key secret. |
| `CHAT_API_KEY_SECRET_REF` | Lambda env var containing ARN | `arn:aws:secretsmanager:us-east-2:521170872319:secret:/arte-chatbot-prod/prod/runtime/CHAT_API_KEY-...` | Points Lambda to the chat API key secret. |
| `CHATWOOT_AGENT_BOT_TOKEN_SECRET_REF` | Lambda env var containing ARN | `arn:aws:ssm:us-east-2:521170872319:parameter/arte-chatbot-prod/prod/runtime/CHATWOOT_AGENT_BOT_TOKEN` | Points Lambda to the Chatwoot AgentBot token. |
| `CHATWOOT_WEBHOOK_SECRET_REF` | Lambda env var containing ARN | `arn:aws:ssm:us-east-2:521170872319:parameter/arte-chatbot-prod/prod/runtime/CHATWOOT_WEBHOOK_SECRET` | Points Lambda to the Chatwoot webhook HMAC secret. |

Use app secret names as keys in `backend_runtime_secret_arns`. Terraform derives the Lambda env names by appending `_SECRET_REF`. Do not use `CHATWOOT_AGENT_BOT_TOKEN_SECRET_REF` or `CHATWOOT_WEBHOOK_SECRET_REF` as map keys.

Do not store plaintext production Lambda runtime secrets in Terraform files, committed docs, or `.env.deploy`.

### Local `.env.deploy` for Terraform

`.env.deploy` is a local/manual deployment input file. It is uncommitted, not packaged into Lambda, not loaded by Lambda at runtime, and not used by CI/CD.

| Name | Kind | Example | Meaning |
|---|---|---|---|
| `TF_VAR_backend_hostname` | `.env.deploy` Terraform input | `chatbot.artesolutions.com.co` | Public backend custom domain managed by Terraform. |
| `TF_VAR_frontend_hostname` | `.env.deploy` Terraform input | `<frontend-hostname>` | Public frontend hostname used for CORS/public URL config. |
| `TF_VAR_admin_hostname` | `.env.deploy` Terraform input | `<admin-hostname>` | Public admin hostname used for CORS/public URL config. |
| `TF_VAR_cloudflare_zone_id` | `.env.deploy` Terraform input | `cab3c51956faf03216e2a1ab74e6e399` | Cloudflare zone where Terraform creates ACM validation and backend CNAME records. |
| `TF_VAR_backend_runtime_secret_arns` | `.env.deploy` Terraform input | JSON map of app secret names to ARNs | Values are AWS SSM/Secrets Manager ARNs, not plaintext secrets. |
| `TF_VAR_backend_runtime_environment_variables` | `.env.deploy` Terraform input | JSON map of non-sensitive runtime config | Extra non-sensitive Lambda runtime environment variables. Do not include `AWS_REGION`; Lambda reserves it. |
| `CLOUDFLARE_API_TOKEN` | `.env.deploy` or sourced local token file | `<cloudflare-token>` | Local Terraform provider credential for DNS changes only. Not needed by Lambda or GitHub promotion. |

For production Lambda-only Terraform, `.env.deploy` no longer needs `TF_VAR_vpc_id`, `TF_VAR_public_subnet_id`, `TF_VAR_cloudflare_account_id`, or `TF_VAR_edge_tunnel_secret`.

Minimum production secret ARN map with Chatwoot enabled:

```bash
TF_VAR_backend_runtime_secret_arns='{
  "OPENAI_API_KEY":"arn:aws:ssm:us-east-2:521170872319:parameter/arte-chatbot/prod/openai-api-key",
  "CHAT_API_KEY":"arn:aws:secretsmanager:us-east-2:521170872319:secret:/arte-chatbot-prod/prod/runtime/CHAT_API_KEY-...",
  "CHATWOOT_AGENT_BOT_TOKEN":"arn:aws:ssm:us-east-2:521170872319:parameter/arte-chatbot-prod/prod/runtime/CHATWOOT_AGENT_BOT_TOKEN",
  "CHATWOOT_WEBHOOK_SECRET":"arn:aws:ssm:us-east-2:521170872319:parameter/arte-chatbot-prod/prod/runtime/CHATWOOT_WEBHOOK_SECRET"
}'
```

Minimum non-sensitive runtime map with Chatwoot enabled:

```bash
TF_VAR_backend_runtime_environment_variables='{
  "APP_ENV":"production",
  "CHATWOOT_ENABLED":"true",
  "CHATWOOT_API_URL":"https://chatwoot.example.com",
  "CHATWOOT_ACCOUNT_ID":"1",
  "CHATWOOT_INBOX_ID":"7"
}'
```

### Lambda runtime variables created by Terraform

Operators do not set these directly in GitHub. Terraform creates them on the Lambda function.

| Name | Kind | Example | Meaning |
|---|---|---|---|
| `APP_ENV` | Lambda env var | `prod` or `production` | Runtime environment label. |
| `AWS_BUCKET_NAME` | Lambda env var | `arte-chatbot-fichas-tecnicas` | S3 bucket containing `index/catalog_index.json` and product PDFs. |
| `STATE_BACKEND` | Lambda env var | `dynamodb` | Enables durable DynamoDB-backed sessions, ownership, rate counters, and buffer state. |
| `DYNAMODB_STATE_TABLE_NAME` | Lambda env var | `arte-chatbot-prod-backend-lambda-state` | DynamoDB state table used by the Lambda backend. |
| `DYNAMODB_STATE_KEY_PREFIX` | Lambda env var | `prod` | Prefix that isolates production keys inside the state table. |
| `SESSION_TTL_SECONDS` | Lambda env var | `2592000` | TTL for persisted session/turn/token items. |
| `BUFFER_TTL_SECONDS` | Lambda env var | `86400` | TTL for multi-message buffer and polling items. |
| `RATE_LIMIT_TTL_SECONDS` | Lambda env var | `86400` | TTL for shared rate-limit counter rows. |
| `LAMBDA_TIMEOUT_SECONDS` | Lambda env var | `25` | App-side timeout budget aligned below API Gateway/Lambda timeout. |
| `ALLOWED_CORS_ORIGINS` | Lambda env var | `https://app.example.com,https://admin.example.com` | Browser origins allowed in production. No wildcard. |
| `PUBLIC_API_URL` | Lambda env var | `https://chatbot.artesolutions.com.co` | Public API URL advertised to clients after cutover. |
| `PUBLIC_FRONTEND_URL` | Lambda env var | `https://<frontend-hostname>` | Public frontend origin allowed by CORS. |
| `PUBLIC_ADMIN_URL` | Lambda env var | `https://<admin-hostname>` | Public admin origin allowed by CORS. |
| `CHATWOOT_ENABLED` | Lambda env var from `backend_runtime_environment_variables` | `true` | Enables `/webhook/chatwoot` processing. Set `false` for rollback. |
| `CHATWOOT_API_URL` | Lambda env var from `backend_runtime_environment_variables` | `https://chatwoot.example.com` | Chatwoot base URL, without a trailing slash. |
| `CHATWOOT_ACCOUNT_ID` | Lambda env var from `backend_runtime_environment_variables` | `1` | Numeric Chatwoot account ID used in API paths and durable mappings. |
| `CHATWOOT_INBOX_ID` | Lambda env var from `backend_runtime_environment_variables` | `7` | Numeric Chatwoot inbox ID for the WhatsApp channel. |
| `CHATWOOT_HANDOFF_TEAM_ID` | Optional Lambda env var from `backend_runtime_environment_variables` | `55` | Team assigned during human escalation. |
| `CHATWOOT_BOT_LABEL` | Optional Lambda env var from `backend_runtime_environment_variables` | `bot` | Label used for bot-owned conversations. |
| `CHATWOOT_ESCALATED_LABEL` | Optional Lambda env var from `backend_runtime_environment_variables` | `escalated` | Label applied during escalation. |
| `CHATWOOT_TECHNICAL_LABEL` | Optional Lambda env var from `backend_runtime_environment_variables` | `technical` | Label for technical intent routing. |
| `CHATWOOT_QUOTE_LABEL` | Optional Lambda env var from `backend_runtime_environment_variables` | `quote` | Label for quote intent routing. |
| `CHATWOOT_ORDER_LABEL` | Optional Lambda env var from `backend_runtime_environment_variables` | `order` | Label for order intent routing. |
| `AWS_REGION` | Reserved Lambda env var | `us-east-2` | Set automatically by AWS Lambda. Do not configure it yourself. |

## CI/CD flow

| Stage | Gate |
|---|---|
| Lint | Ruff, format check, dependency audit, syntax check. |
| Tests | Targeted Lambda/runtime/state/delivery tests run before packaging. |
| Package | `uv run python scripts/build_lambda_package.py` builds `dist/lambda/backend.zip` with the same Python minor version as the Terraform Lambda runtime. |
| Package scan | The zip is scanned for `.env`, `.env.deploy`, `.aws`, credentials, and obvious plaintext secret markers. |
| Staging deploy | OIDC assumes `AWS_DEPLOY_ROLE_ARN`; the scanned artifact is published to the staging Lambda alias. |
| Staging smoke | Direct endpoint validates `/health`, `/chat`, File Inputs/source docs, DynamoDB rows, IAM-denied probe, and production URL isolation. |
| Staging evaluation | Evaluation harness runs against the same staging endpoint with S3 upload disabled. |
| Cutover prerequisite | Production Terraform is Lambda-only and contains no EC2 Compose/Cloudflare Tunnel wiring. |
| Production promotion | The same package SHA is uploaded to production and the production alias is moved to the new published version. |
| Production smoke | Production custom domain validates `/health`, `/chat`, and DynamoDB persistence. |
| Rollback | Previous alias version is captured before promotion and can be restored automatically or manually. |

## Multi-message buffering on Lambda

Lambda does not rely on delayed `asyncio.create_task` execution after returning
`202 Accepted`. When `STATE_BACKEND=dynamodb`, each buffered message is stored
in DynamoDB and `/buffer-result/{session_id}` is the durable polling trigger:

1. `/chat` stores the message and returns `202` with a poll URL.
2. The client polls `/buffer-result/{session_id}`.
3. If the debounce window has elapsed since the last stored message, the poll
   request flushes the durable buffer, processes the joined message, and returns
   the ready result.
4. If the window has not elapsed or another poll is processing, the endpoint
   returns `pending`.

Local memory mode still uses in-process debounce tasks for developer ergonomics;
that behavior is not treated as Lambda durability.

## Rollback runbook

### Lambda alias rollback

Use when the Lambda package or runtime behavior regresses after alias promotion.

```bash
uv run python scripts/lambda_rollback.py discover-alias \
  --aws-region us-east-2 \
  --function-name "$LAMBDA_PROD_FUNCTION_NAME" \
  --alias-name "${LAMBDA_PROD_ALIAS_NAME:-live}"

uv run python scripts/lambda_rollback.py rollback-alias \
  --aws-region us-east-2 \
  --function-name "$LAMBDA_PROD_FUNCTION_NAME" \
  --alias-name "${LAMBDA_PROD_ALIAS_NAME:-live}" \
  --target-version "$PREVIOUS_VERSION"
```

Then rerun production `/health` and `/chat` smoke checks.

The EC2 fallback route is intentionally unavailable after this cutover. Rollback is Lambda-version only: restore the previous alias target and rerun production smoke checks.

## Feature-branch-chain boundary

This work is the fourth chained PR slice:

| Slice | Scope |
|---|---|
| PR 1 | Lambda-safe state and DynamoDB repository. |
| PR 2 | Lambda runtime, Mangum handler, and package exclusions. |
| PR 3 | Terraform Lambda/API/DynamoDB/IAM/staging infrastructure. |
| PR 4 | CI/CD package gates, staging smoke/evaluation, rollback, and cutover docs. |

Child PRs should target the previous slice branch, not `main`, until the tracker PR aggregates the feature branch.

## Roadmap exclusions

Do not implement these as part of the first Lambda cutover:

- WAF/API Gateway advanced throttling beyond basic HTTP API readiness.
- SQS/EventBridge/Step Functions durable workflow redesign.
- Async chat jobs with polling/webhooks for slow File Inputs.
- Dashboards, alarms, X-Ray, or OpenTelemetry beyond existing logs.

Track them after the Lambda migration is healthy in production.

## Verification checklist

- [ ] Lambda package artifact SHA is recorded and reused for staging and production.
- [ ] Package scan confirms `.env`, `.env.deploy`, and plaintext credentials are absent.
- [ ] Staging direct endpoint is not a production URL.
- [ ] Staging `/chat` returns source documents for a datasheet-backed prompt.
- [ ] Staging DynamoDB table contains the smoke session rows.
- [ ] IAM-denied probe fails with an authorization error.
- [ ] Production alias rollback target is captured before promotion.
- [ ] Production Terraform plan/apply succeeds without VPC/subnet/tunnel secret variables.
