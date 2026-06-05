# Fargate + Cloudflare Deployment Guide

Production CD is live for backend, frontend, and admin containers on AWS ECS Fargate, exposed through scoped Cloudflare Tunnel sidecars. GitHub Actions builds and evaluates images first; only `main` can publish release tags and apply production Terraform.

## Current production status

| Area | Status |
|---|---|
| CD workflow | Live; `deploy-production` runs only on `push` to `main`. |
| Last verified run | GitHub Actions run `26991613251` passed lint, build, health, evaluation, release publish, and production ECS deploy. |
| Public API | `https://chatbot.artesolutions.com.co/health` returned healthy JSON during SDD verify. |
| Public app | `https://app.artesolutions.com.co` returned HTTP 200 during SDD verify. |
| Public admin | `https://admin.artesolutions.com.co` returned HTTP 200 during SDD verify. |
| Known tradeoff | `PROD_ASSIGN_PUBLIC_IP=true` is the short-term egress fix until NAT/VPC endpoints are provisioned. |

## Quick path

1. Open a PR and let CI build, test, health-check, and evaluate the images.
2. Confirm candidate tags exist in ECR, for example `pr-123-sha-<commit>` and `sha-<commit>`.
3. Merge to `main`; the workflow pushes `sha-<commit>` release tags and applies `infra/terraform/envs/prod`.
4. Verify the three public Cloudflare endpoints.
5. If validation was done through local staging, destroy it before its expiration timestamp.

## Required GitHub configuration

### Secrets

| Secret | Purpose |
|---|---|
| `AWS_CI_ROLE_ARN` | OIDC role used by CI image/evaluation jobs that need AWS access. |
| `AWS_DEPLOY_ROLE_ARN` | OIDC role used by production deploy. |
| `OPENAI_API_KEY` | Runtime/evaluation OpenAI credential. |
| `CHAT_API_KEY` | API auth key used by health/evaluation flows. |
| `AWS_BUCKET_NAME` | S3 bucket for catalog and PDF data. |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token for Terraform-managed tunnels/DNS. |
| `PROD_BACKEND_TUNNEL_SECRET` | Backend Cloudflare tunnel secret. |
| `PROD_FRONTEND_TUNNEL_SECRET` | Frontend Cloudflare tunnel secret. |
| `PROD_ADMIN_TUNNEL_SECRET` | Admin Cloudflare tunnel secret. |
| `PROD_BACKEND_RUNTIME_SECRET_ARNS_JSON` | JSON map of backend ECS secret names to Secrets Manager/SSM ARNs, including `OPENAI_API_KEY` and `CHAT_API_KEY`. |

### Variables

| Variable | Purpose |
|---|---|
| `AWS_REGION` | AWS region; current deploy defaults to `us-east-2` if unset in the workflow expression. |
| `BACKEND_ECR_REPOSITORY_URL` | Backend ECR repository URL. |
| `FRONTEND_ECR_REPOSITORY_URL` | Frontend ECR repository URL. |
| `ADMIN_ECR_REPOSITORY_URL` | Admin ECR repository URL. |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account id used by Terraform. |
| `CLOUDFLARE_ZONE_ID` | Cloudflare zone id for `artesolutions.com.co`. |
| `PROD_VPC_ID` | Production VPC id for ECS services. |
| `PROD_PRIVATE_SUBNET_IDS_JSON` | JSON list of subnet ids for Fargate tasks. |
| `PROD_ASSIGN_PUBLIC_IP` | Temporary egress switch. Currently `true`; prefer `false` after NAT/VPC endpoints exist. |

## Production deploy flow

| Step | Gate |
|---|---|
| Build | Backend, frontend, and admin Docker images are built from separate Dockerfiles. |
| Health | Backend container must answer `/health`. |
| Evaluation | The evaluation harness must pass before any release image push. |
| ECR publish | Immutable `sha-${GITHUB_SHA}` tags are pushed. PRs also get `pr-<number>-sha-${GITHUB_SHA}` candidate tags. |
| Deploy | `deploy-production` runs only for `push` on `refs/heads/main` and assumes `AWS_DEPLOY_ROLE_ARN` through GitHub OIDC. |

Production Terraform root: `infra/terraform/envs/prod/`.

Production hostnames:

| Service | Hostname |
|---|---|
| Backend API | `chatbot.artesolutions.com.co` |
| Frontend | `app.artesolutions.com.co` |
| Admin | `admin.artesolutions.com.co` |

## Post-deploy verification

```bash
curl -fsS https://chatbot.artesolutions.com.co/health
curl -fsSIL https://app.artesolutions.com.co
curl -fsSIL https://admin.artesolutions.com.co
```

Expected result:

- Backend returns healthy JSON.
- Frontend and admin return HTTP 200.
- The GitHub Actions deploy run is green.

## Rollback runbook

Use rollback when a `main` deploy passes infrastructure apply but runtime behavior regresses.

1. Pick the previous known-good `sha-<commit>` image tag or ECS task definition revision from the prior successful deploy.
2. Re-run Terraform from `infra/terraform/envs/prod` with the previous image tags for backend, frontend, and admin.
3. Wait for ECS services to stabilize.
4. Re-run the post-deploy verification checks above.
5. If tunnel credentials changed during the bad deploy, rotate or revoke the replaced Cloudflare tunnel secrets after the rollback is healthy.

Rollback is possible because release images use SHA-based tags and ECS registers task definition revisions per deploy.

## IAM and credentials

Deployed ECS tasks use IAM roles and the AWS SDK default credential provider chain. Do not inject long-lived `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` into production ECS tasks.

For local development, use a normal AWS credential-chain source:

- `AWS_PROFILE`
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN`
- `aws sso login`
- environment-provided temporary credentials

## Network egress follow-up

`PROD_ASSIGN_PUBLIC_IP=true` is currently accepted as a short-term production unblocker. The stronger production posture is:

1. Add NAT Gateway or the required VPC endpoints for AWS dependencies.
2. Keep outbound HTTPS available for Cloudflare Tunnel connectors.
3. Set `PROD_ASSIGN_PUBLIC_IP=false`.
4. Redeploy and verify the three public endpoints.

Do NOT flip this variable blindly. This is one of those places where speed without understanding bites: if tasks cannot reach Secrets Manager, S3, ECR, logs, or Cloudflare, ECS will fail even if Terraform applies cleanly.

## Local staging

Local staging is intentionally not a CI workflow. It must run from a developer machine and uses isolated state, names, hostnames, tunnel secrets, SSM parameters, and Secrets Manager entries.

Example:

```bash
scripts/deploy-local-staging.sh \
  --staging-id pr-123 \
  --backend-tag pr-123-sha-abcdef1 \
  --frontend-tag pr-123-sha-abcdef1 \
  --admin-tag pr-123-sha-abcdef1 \
  --plan-only
```

The script rejects:

- CI/GitHub Actions execution
- missing or implicit tags such as `latest` or `bootstrap`
- production-like staging ids such as `api`, `app`, `admin`, `prod`, or `main`
- expiration timestamps more than three days from now

Local staging hostnames are derived from the staging id:

| Service | Pattern |
|---|---|
| Backend API | `staging-chatbot-api-<id>.artesolutions.com.co` |
| Frontend | `staging-chatbot-<id>.artesolutions.com.co` |
| Admin | `staging-chatbot-admin-<id>.artesolutions.com.co` |

Destroy when done:

```bash
scripts/deploy-local-staging.sh \
  --staging-id pr-123 \
  --backend-tag pr-123-sha-abcdef1 \
  --frontend-tag pr-123-sha-abcdef1 \
  --admin-tag pr-123-sha-abcdef1 \
  --destroy
```

## Verification checklist

- [ ] PR workflow built all three images.
- [ ] Health and evaluation gates passed before image publishing.
- [ ] PR did not run `deploy-production`.
- [ ] ECR contains rollback-visible SHA tags.
- [ ] `main` deploy used GitHub OIDC, not long-lived static AWS keys.
- [ ] ECS task role can read the S3 catalog/PDF bucket.
- [ ] Cloudflare hostnames route to same-task localhost origins.
- [ ] Public API, app, and admin endpoints respond after deploy.
- [ ] Local staging has an expiration no later than three days and is destroyed after validation.
