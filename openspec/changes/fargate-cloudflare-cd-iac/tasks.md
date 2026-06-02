# Tasks: Fargate Cloudflare CD IaC

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 1200-1800 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 runtime fixes → PR2 Terraform foundation → PR3 CD/staging/docs |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|---|---|---|---|
| 1 | Backend deploy config works with IAM credentials | PR 1 | CORS/S3 changes plus tests |
| 2 | AWS/Cloudflare IaC defines prod services | PR 2 | Terraform modules/root, separate images/services |
| 3 | CD and local staging are guarded | PR 3 | Workflows, staging script, docs |

## Phase 1: Runtime Foundation

- [x] 1.1 Update `backend/app/config.py` with `APP_ENV`, `PUBLIC_API_URL`, `PUBLIC_FRONTEND_URL`, `PUBLIC_ADMIN_URL`, and `ALLOWED_CORS_ORIGINS`; fail prod when origins are missing or wildcard.
- [x] 1.2 Update `backend/main.py` to use configured CORS origins and stop treating static AWS keys as required deployed env.
- [x] 1.3 Update `backend/app/s3_client.py`, `evaluation/s3_client.py`, `evaluation/storage.py`, and `evaluation/harness/s3_upload.py` to use the AWS default credential chain when explicit local keys are absent.
- [x] 1.4 Add/extend `backend/tests/test_config.py`, `backend/tests/test_s3_client.py`, `evaluation/harness/tests/test_s3_upload.py`, and evaluation storage tests for CORS prod fail-fast, local origins, and boto3 client args.

## Phase 2: Terraform Infrastructure

- [x] 2.1 Create `infra/terraform/modules/{ecr,ecs_service,cloudflare_tunnel,ssm_secrets,github_oidc}/` with variables, outputs, least-privilege IAM, logs, SGs, sidecar support, and sensitive tunnel token handling.
- [x] 2.2 Create `infra/terraform/envs/prod/` root with variable-driven `DOMAIN_NAME` defaulting to `artesolutions.com.co`, hostnames `api`, `app`, and `admin`, and separate backend/frontend/admin ECR repos, task definitions, services, and cloudflared sidecars.
- [x] 2.3 Create `admin/Dockerfile`, `admin/nginx.conf`, and minimal admin image source if absent; keep admin as a separate image/service, not a frontend route.
- [x] 2.4 Add Terraform validation/tests for scoped tunnels, no shared unreachable localhost origins, sensitive outputs, and prod/staging name isolation.

## Phase 3: CD and Staging

- [ ] 3.1 Modify `.github/workflows/ci.yml` to build backend, frontend, and admin images; push immutable PR candidate tags after tests/evaluation; deploy prod only on `main` using OIDC.
- [ ] 3.2 Create `scripts/deploy-local-staging.sh` and `infra/terraform/envs/local-staging/` requiring explicit ECR tags, unique staging hostnames, non-CI execution, isolated state/secrets/params, and expiration no later than 3 days.
- [ ] 3.3 Add workflow/staging guard checks for PR no-prod-deploy, CI staging rejection, production URL/name rejection, and rollback-visible SHA tags.

## Phase 4: Documentation

- [ ] 4.1 Update `.env.example`, `README.md`, and deployment docs with `DOMAIN_NAME=artesolutions.com.co`, IAM/default credential-chain usage, ECR tags, prod deploy flow, and local staging cleanup.
