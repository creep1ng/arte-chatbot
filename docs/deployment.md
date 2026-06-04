# Fargate + Cloudflare Deployment Guide

This project deploys backend, frontend, and admin containers to AWS ECS Fargate and exposes them through scoped Cloudflare Tunnel sidecars. CI can publish immutable ECR tags after gates pass; only `main` deploys production.

## Quick path

1. Provision or confirm AWS, Cloudflare, and GitHub deploy inputs.
2. Let PR CI build/test/evaluate and publish candidate tags such as `pr-123-sha-<commit>` and `sha-<commit>`.
3. Merge to `main`; the workflow pushes `sha-<commit>` tags and applies the production Terraform root with those tags.
4. For manual public validation before merge, run local staging from a developer machine with explicit ECR tags.
5. Destroy local staging before or at its expiration timestamp.

## Required access

| Area | Required input |
|------|----------------|
| AWS | Account permissions for ECR, ECS/Fargate, IAM pass role, CloudWatch Logs, S3, SSM, Secrets Manager, and Terraform state access. |
| Cloudflare | Account id, zone id for `artesolutions.com.co`, and API token capable of managing tunnels/DNS. |
| GitHub Actions secrets | `AWS_CI_ROLE_ARN`, `AWS_DEPLOY_ROLE_ARN`, `OPENAI_API_KEY`, `CHAT_API_KEY`, `AWS_BUCKET_NAME`. |
| GitHub Actions variables | `AWS_REGION`, `BACKEND_ECR_REPOSITORY_URL`, `FRONTEND_ECR_REPOSITORY_URL`, `ADMIN_ECR_REPOSITORY_URL`. |
| Terraform prod vars | VPC/subnets, Cloudflare ids/secrets, runtime secret ARNs, and `DOMAIN_NAME=artesolutions.com.co`. |
| Local `.env` | Local-only OpenAI/chat keys and optional AWS default credential-chain settings. |

## Production deploy flow

| Step | Gate |
|------|------|
| Build | Backend, frontend, and admin Docker images are built from their separate Dockerfiles. |
| Health | Backend container must answer `/health`. |
| Evaluation | The evaluation harness must pass before any image push. |
| ECR publish | Immutable `sha-${GITHUB_SHA}` tags are pushed. PRs also get `pr-<number>-sha-${GITHUB_SHA}` candidate tags. |
| Deploy | `deploy-production` runs only for `push` on `refs/heads/main` and assumes `AWS_DEPLOY_ROLE_ARN` through GitHub OIDC. |

Production Terraform root: `infra/terraform/envs/prod/`.

Production hostnames default to:

| Service | Hostname |
|---------|----------|
| Backend API | `chatbot.artesolutions.com.co` |
| Frontend | `app.artesolutions.com.co` |
| Admin | `admin.artesolutions.com.co` |

## IAM and credentials

Deployed ECS tasks use IAM roles and the AWS SDK default credential provider chain. Do not inject long-lived `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` into production ECS tasks.

For local development, you may use any standard AWS credential-chain source:

- `AWS_PROFILE`
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN`
- `aws sso login`
- environment-provided temporary credentials

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
|---------|---------|
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
- [ ] Local staging has an expiration no later than three days and is destroyed after validation.
