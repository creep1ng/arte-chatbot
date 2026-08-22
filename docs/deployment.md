# Lambda Serverless Deployment Guide

Production cutover moves the backend from EC2 Compose/Cloudflare Tunnel to AWS Lambda behind API Gateway HTTP API. The production Terraform root is now Lambda-only: the EC2 Compose host, Cloudflare Tunnel, and SSM Run Command deploy path were intentionally removed as a destructive cutover. Frontend and admin image delivery stay on the existing ECR path.

## Current production status

| Area | Status |
|---|---|
| Backend target | Lambda + API Gateway HTTP API is the cutover target. |
| Existing path | EC2 Compose/Cloudflare Tunnel production fallback has been removed. |
| Staging | PR previews deploy the same scanned package artifact to isolated non-production direct endpoints. Fixed Lambda staging is optional and no longer blocks production cutover when disabled. |
| Production Terraform inputs | `TF_VAR_vpc_id`, `TF_VAR_public_subnet_id`, `TF_VAR_cloudflare_account_id`, and `TF_VAR_edge_tunnel_secret` are no longer required. `TF_VAR_cloudflare_zone_id` plus `CLOUDFLARE_API_TOKEN` are used only to manage the backend custom-domain DNS record. |
| Backend custom domain | `https://chatbot.artesolutions.com.co` is expected to work only after Terraform creates the API Gateway custom domain, ACM DNS validation record, API mapping, and Cloudflare CNAME. The direct `execute-api` URL may work before this. |
| Session reset policy | No live EC2 sessions exist; cutover may reset in-memory sessions. Durable Lambda state starts in DynamoDB. |

## Quick path

1. Open the fourth feature-branch-chain PR for delivery gates only.
2. Let CI lint, run targeted tests, build `dist/lambda/backend.zip`, and scan the package for `.env`, `.env.deploy`, and plaintext credentials.
3. For PRs, deploy/update the Lambda preview from the scanned artifact and smoke its direct API Gateway endpoint.
4. Run preview `/health`, authenticated `/chat`, S3 File Inputs, DynamoDB persistence, optional IAM-denied negative probe, and production URL isolation checks.
5. Plan/apply `infra/terraform/envs/prod` with Lambda-only inputs; do not provide VPC, public subnet, Cloudflare account, or tunnel secret variables. Provide Cloudflare zone/token only for DNS custom-domain management.
6. Enable Lambda cutover variables and promote the same package hash to the production Lambda alias. Fixed Lambda staging runs only when `LAMBDA_STAGING_ENABLED=true`.
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
| `LAMBDA_STAGING_ENABLED` | GitHub Variable | `false` | Enables the legacy fixed Lambda staging gate before production cutover. Keep `false` when only PR previews are configured. |
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
| `LAMBDA_PREVIEW_ENABLED` | GitHub Variable | `true` | Enables per-PR Lambda previews for same-repository PRs. |
| `TF_PREVIEW_STATE_BUCKET` | GitHub Variable | `arte-chatbot-terraform-state` | S3 bucket used by the preview Terraform backend. Defaults to this value in workflows. |
| `TF_PREVIEW_STATE_PREFIX` | GitHub Variable | `lambda-previews` | S3 key prefix for per-PR Terraform state, producing keys like `lambda-previews/pr-220/terraform.tfstate`. |
| `LAMBDA_PREVIEW_RUNTIME_ENV_JSON` | GitHub Variable | `{"LOG_LEVEL":"INFO"}` | Optional non-sensitive preview runtime environment variables. |
| `LAMBDA_PREVIEW_ALLOWED_CORS_ORIGINS` | GitHub Variable | `*` | Comma-separated CORS origins for direct preview API Gateway URLs. Defaults to `*`. |
| `LAMBDA_PREVIEW_IAM_DENIED_DYNAMODB_TABLE_NAME` | GitHub Variable | `<denied-table-name>` | Optional resource expected to fail the IAM-denied preview probe. |
| `LAMBDA_PREVIEW_SMOKE_CHAT_MESSAGE` | GitHub Variable | `Validación preview PR: ...` | Optional preview smoke prompt. |

`PROD_BACKEND_RUNTIME_ENV_JSON` is **not used by the current workflow**. Runtime environment values are applied by Terraform through `.env.deploy`, not by GitHub promotion jobs.

### GitHub Repository Secrets

GitHub Secrets are sensitive values used by workflow jobs. They are not read by Lambda at runtime unless a workflow explicitly injects them into a command.

| Name | Kind | Example | Meaning |
|---|---|---|---|
| `AWS_CI_ROLE_ARN` | GitHub Secret | `arn:aws:iam::521170872319:role/<ci-role>` | OIDC role used by CI jobs that need AWS access. |
| `AWS_DEPLOY_ROLE_ARN` | GitHub Secret | `arn:aws:iam::521170872319:role/<deploy-role>` | OIDC role used by staging/prod Lambda deploy jobs. |
| `AWS_PREVIEW_DEPLOY_ROLE_ARN` | GitHub Secret | `arn:aws:iam::521170872319:role/<preview-deploy-role>` | OIDC role used to apply/destroy per-PR preview Terraform. Falls back to `AWS_DEPLOY_ROLE_ARN` if omitted. |
| `LAMBDA_PREVIEW_RUNTIME_SECRET_ARNS_JSON` | GitHub Secret | `{"OPENAI_API_KEY":"arn:...","CHAT_API_KEY":"arn:..."}` | SSM/Secrets Manager ARNs injected into preview Lambda as secret refs. The preview smoke job resolves the same `CHAT_API_KEY` ARN through AWS CLI, masks the value, and uses it for `/chat` and evaluation. Preview-scoped ARNs are preferred, but shared runtime ARNs are allowed while bootstrapping previews. |
| `LAMBDA_PREVIEW_KMS_KEY_ARNS_JSON` | GitHub Secret | `["arn:aws:kms:..."]` | Optional KMS keys needed to decrypt preview runtime secret refs. Use `[]` or omit it when no custom KMS key is needed. |
| `OPENAI_API_KEY` | GitHub Secret | `<openai-api-key>` | CI/evaluation plaintext credential. Lambda production runtime should use AWS SSM/Secrets Manager instead. |
| `CHAT_API_KEY` | GitHub Secret | `<chat-api-key>` | Plaintext API key used by production smoke checks. Do not put the Secrets Manager ARN here. |
| `AWS_BUCKET_NAME` | GitHub Secret | `arte-chatbot-fichas-tecnicas` | S3 bucket used by CI/evaluation jobs and preview Lambda catalog reads. |
| `PROD_BACKEND_HOSTNAME` | GitHub Secret | `chatbot.artesolutions.com.co` | Masked production hostname used only as a forbidden URL during staging isolation checks. |
| `LAMBDA_STAGING_CHAT_API_KEY` | GitHub Secret | `<staging-chat-api-key>` | Plaintext staging `/chat` API key for fixed staging smoke. Required only when `LAMBDA_STAGING_ENABLED=true` or manual staging deploy is used. |

`PROD_BACKEND_RUNTIME_SECRET_ARNS_JSON` is **not used by the current workflow**. Runtime secret ARNs are Terraform inputs in `.env.deploy`. Keep this secret only if another operator workflow consumes it later.

### AWS SSM Parameter Store / Secrets Manager

Lambda runtime secrets live in AWS, not in GitHub. Terraform passes only ARNs into Lambda as `*_SECRET_REF` environment variables, and the Lambda execution role reads the secret values at runtime.

| Name | Kind | Example | Meaning |
|---|---|---|---|
| `/arte-chatbot/prod/OPENAI_API_KEY` | SSM SecureString or Secrets Manager secret | `sk-proj-...` | Production OpenAI key read by Lambda as `OPENAI_API_KEY`. |
| `/arte-chatbot-prod/prod/runtime/CHAT_API_KEY` | Secrets Manager secret | `<chat-api-key>` | Production `/chat` API key read by Lambda as `CHAT_API_KEY`. |

The Lambda environment variable names are generated by Terraform from `backend_runtime_secret_arns`:

| Lambda env name | Kind | Example | Meaning |
|---|---|---|---|
| `OPENAI_API_KEY_SECRET_REF` | Lambda env var containing ARN | `arn:aws:ssm:us-east-2:521170872319:parameter/arte-chatbot/prod/OPENAI_API_KEY` | Points Lambda to the OpenAI key secret. |
| `CHAT_API_KEY_SECRET_REF` | Lambda env var containing ARN | `arn:aws:secretsmanager:us-east-2:521170872319:secret:/arte-chatbot-prod/prod/runtime/CHAT_API_KEY-...` | Points Lambda to the chat API key secret. |

Do not store plaintext production Lambda runtime secrets in Terraform files, committed docs, or `.env.deploy`.

### Local `.env.deploy` for Terraform

`.env.deploy` is a local/manual deployment input file. It is uncommitted, not packaged into Lambda, not loaded by Lambda at runtime, and not used by CI/CD.

| Name | Kind | Example | Meaning |
|---|---|---|---|
| `TF_VAR_backend_hostname` | `.env.deploy` Terraform input | `chatbot.artesolutions.com.co` | Public backend custom domain managed by Terraform. |
| `TF_VAR_frontend_hostname` | `.env.deploy` Terraform input | `<frontend-hostname>` | Public frontend hostname used for CORS/public URL config. |
| `TF_VAR_admin_hostname` | `.env.deploy` Terraform input | `<admin-hostname>` | Public admin hostname used for CORS/public URL config. |
| `TF_VAR_cloudflare_zone_id` | `.env.deploy` Terraform input | `cab3c51956faf03216e2a1ab74e6e399` | Cloudflare zone where Terraform creates ACM validation and backend CNAME records. |
| `TF_VAR_backend_runtime_secret_arns` | `.env.deploy` Terraform input | `{"OPENAI_API_KEY":"arn:aws:ssm:us-east-2:521170872319:parameter/...","CHAT_API_KEY":"arn:aws:secretsmanager:us-east-2:521170872319:secret:..."}` | Map from app secret names to AWS SSM/Secrets Manager ARNs. Values are ARNs, not plaintext secrets. |
| `TF_VAR_backend_runtime_environment_variables` | `.env.deploy` Terraform input | `{"APP_ENV":"production"}` | Extra non-sensitive Lambda runtime environment variables. Do not include `AWS_REGION`; Lambda reserves it. |
| `CLOUDFLARE_API_TOKEN` | `.env.deploy` or sourced local token file | `<cloudflare-token>` | Local Terraform provider credential for DNS changes only. Not needed by Lambda or GitHub promotion. |

For production Lambda-only Terraform, `.env.deploy` no longer needs `TF_VAR_vpc_id`, `TF_VAR_public_subnet_id`, `TF_VAR_cloudflare_account_id`, or `TF_VAR_edge_tunnel_secret`.

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
| `AWS_REGION` | Reserved Lambda env var | `us-east-2` | Set automatically by AWS Lambda. Do not configure it yourself. |

## CI/CD flow

| Stage | Gate |
|---|---|
| Lint | Ruff, format check, dependency audit, syntax check. |
| Tests | Targeted Lambda/runtime/state/delivery tests run before packaging. |
| Package | `uv run python scripts/build_lambda_package.py` builds `dist/lambda/backend.zip` with the same Python minor version as the Terraform Lambda runtime. |
| Package scan | The zip is scanned for `.env`, `.env.deploy`, `.aws`, credentials, and obvious plaintext secret markers. |
| PR preview deploy | On same-repository PRs with `LAMBDA_PREVIEW_ENABLED=true`, OIDC assumes `AWS_PREVIEW_DEPLOY_ROLE_ARN` and applies `infra/terraform/envs/pr-preview` with state key `lambda-previews/pr-<number>/terraform.tfstate`. |
| PR preview smoke | Direct endpoint validates `/health`, `/chat`, File Inputs/source docs, DynamoDB rows, optional IAM-denied probe, and production URL isolation. The job reads the chat API key from the same `CHAT_API_KEY` ARN configured in the `LAMBDA_PREVIEW_RUNTIME_SECRET_ARNS_JSON` GitHub Secret; no duplicate GitHub plaintext key is required. |
| PR preview evaluation | Evaluation harness runs against the same preview endpoint with S3 upload disabled; the workflow comments the URL and validation result on the PR. |
| PR preview cleanup | `.github/workflows/lambda-preview-cleanup.yml` destroys the per-PR Terraform state when the PR closes or merges. |
| Fixed staging deploy | Optional. When `LAMBDA_STAGING_ENABLED=true`, OIDC assumes `AWS_DEPLOY_ROLE_ARN`; the scanned artifact is published to the fixed staging Lambda alias. |
| Fixed staging smoke | Optional. Direct endpoint validates `/health`, `/chat`, File Inputs/source docs, DynamoDB rows, IAM-denied probe, and production URL isolation. |
| Cutover prerequisite | Production Terraform is Lambda-only and contains no EC2 Compose/Cloudflare Tunnel wiring. |
| Production promotion | The same package SHA is uploaded to production and the production alias is moved to the new published version. |
| Production smoke | Production custom domain validates `/health`, `/chat`, and DynamoDB persistence. |
| Rollback | Previous alias version is captured before promotion and can be restored automatically or manually. |

## PR preview environments

The PR preview path creates one isolated Lambda/API Gateway/DynamoDB stack per same-repository PR:

1. `lambda-package` builds and scans `dist/lambda/backend.zip`.
2. `deploy-lambda-preview` downloads that artifact, initializes S3 Terraform state at `TF_PREVIEW_STATE_PREFIX/pr-<number>/terraform.tfstate`, and applies `infra/terraform/envs/pr-preview`.
3. `smoke-lambda-preview` validates the direct API Gateway URL, source documents, and the preview DynamoDB table/prefix.
4. `comment-lambda-preview` upserts a PR comment with the API URL, Lambda function, state table/prefix, package SHA, validation result, and cleanup deadline.
5. `lambda-preview-cleanup.yml` runs on PR close/merge and destroys the same Terraform state.

Preview resources are tagged with `Environment=pr-preview`, `PreviewId=pr-<number>`, `PullRequest=<number>`, `ExpiresAt`, and `CleanupAfter`. These tags are the orphan-resource guardrail if a workflow is cancelled before cleanup.

### Provision preview AWS authority

The production Terraform root owns one GitHub OIDC provider and creates two roles with non-overlapping trust subjects:

| Role | GitHub `sub` | Authority |
|---|---|---|
| Production deploy | `repo:<owner>/arte-chatbot:ref:refs/heads/main` | Existing production promotion permissions only; it cannot create preview Lambda, DynamoDB, API Gateway, or IAM resources. |
| Preview deploy | `repo:<owner>/arte-chatbot:pull_request` | Preview-prefixed infrastructure, isolated Terraform state, preview-scoped runtime secrets, and `iam:PassRole` for the single foundation-managed preview execution role. |

Set `create_github_oidc_role=true` and apply `infra/terraform/envs/prod` from a trusted operator context. Then copy these outputs into GitHub configuration:

1. `github_preview_deploy_role_arn` → secret `AWS_PREVIEW_DEPLOY_ROLE_ARN`.
2. `preview_lambda_permissions_boundary_arn` → variable `LAMBDA_PREVIEW_PERMISSIONS_BOUNDARY_ARN`.
3. `preview_lambda_execution_role_arn` → variable `LAMBDA_PREVIEW_EXECUTION_ROLE_ARN`.

If `arte-chatbot-preview-github-deploy` already exists, import it before planning so Terraform adopts rather than recreates it:

```bash
terraform -chdir=infra/terraform/envs/prod import \
  'module.github_oidc[0].aws_iam_role.preview' \
  arte-chatbot-preview-github-deploy
```

The preview Lambda execution role and its boundary live in the trusted production foundation. Pull-request Terraform only receives their ARNs: it cannot modify either resource. The boundary permits preview-prefixed DynamoDB/log resources, catalog reads, and only SSM/Secrets Manager paths under `/arte-chatbot/pr-preview/`. This remains effective even if a pull request attempts to broaden its generated inline policy.

Previews intentionally use direct API Gateway URLs first. DNS per PR is a later enhancement and is not required for this scope.

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
