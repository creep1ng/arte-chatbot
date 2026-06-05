# Design: Fargate Cloudflare CD IaC

## Technical Approach

Create Terraform-first deployment under `infra/terraform` for AWS ECS Fargate plus Cloudflare Tunnel. V1 keeps backend and frontend/admin containerized, with each exposed ECS service owning its origin container and a same-task `cloudflared` sidecar. Direct IPv4 and EC2 are fallback-only; S3+CloudFront for frontend is deferred.

## Architecture Decisions

| Area | Decision | Tradeoff / rationale |
|------|----------|----------------------|
| Terraform layout | `infra/terraform/modules/{ecr,ecs_service,cloudflare_tunnel,ssm_secrets,github_oidc}` plus roots `envs/prod` and `envs/local-staging` | Keeps reusable service shape while isolating prod/staging state, names, variables, and secrets. |
| Ingress | Backend routes `api` to `http://localhost:8000`; frontend and admin are separate images/services, each with UI hostnames to `http://localhost:3000` | Same-task localhost is simple and avoids ALB. Separate tunnel scopes avoid shared tunnel replicas receiving hostnames whose localhost origin is absent. |
| Runtime credentials | ECS execution role pulls ECR, writes logs, and resolves ECS secret refs; task role grants app S3 access | Matches ECS role boundaries and lets boto3 use the default provider chain instead of static deployed keys. |
| Config/secrets | Store `OPENAI_API_KEY`, `CHAT_API_KEY`, Cloudflare tunnel tokens in Secrets Manager or SSM SecureString; non-secret env via SSM/TF variables | Plaintext stays out of git, task definitions, and Terraform outputs. |
| CD | PRs build/test/evaluate and push immutable candidate tags; `main` registers task definitions and updates prod ECS services | Promotion is gated; prod deploy is main-only. Update only services whose image digest/tag changed where workflow diffing can prove it. |
| Local staging | Developer-run only, explicit ECR image tag required; optional local-pushed tag; hostnames like `staging-chatbot-<id>.example.com`; expiration tag/parameter max 3 days | Staging validates useful public ingress without official prod URLs or CI-created staging. |

## Data Flow

```text
Cloudflare hostname  -> scoped tunnel  -> cloudflared sidecar -> localhost origin
chatbot.$DOMAIN      -> backend tunnel -> backend:8000
app.$DOMAIN          -> frontend tunnel -> frontend:3000
admin.$DOMAIN        -> admin tunnel   -> admin:3000

GitHub PR -> build/test/eval -> ECR candidate tag
main      -> promote SHA tag -> ECS task definition -> ECS service update
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `infra/terraform/modules/ecr/*` | Create | Backend/frontend repositories and lifecycle policy. |
| `infra/terraform/modules/ecs_service/*` | Create | Cluster/service/task definition, logs, SGs, sidecar container definitions, roles. |
| `infra/terraform/modules/cloudflare_tunnel/*` | Create | Tunnel resources, public hostnames, DNS, sensitive token handling. |
| `infra/terraform/modules/ssm_secrets/*` | Create | Parameter/secret references and path conventions. |
| `infra/terraform/modules/github_oidc/*` | Create | Least-privilege deploy role for Actions. |
| `infra/terraform/envs/prod/*` | Create | Prod backend, frontend, and admin services using domain variable defaulting to `artesolutions.com.co`. |
| `infra/terraform/envs/local-staging/*` | Create | Isolated state/names/tokens, explicit image tags, expiration metadata, validation guards. |
| `scripts/deploy-local-staging.sh` | Create | Reject CI, require staging id and ECR tags, pass TF vars. |
| `.github/workflows/ci.yml` | Modify | Build both images, run gates, push candidate tags, deploy prod only on `main`. |
| `backend/app/config.py` | Modify | Add `allowed_cors_origins`, public URL/env validation, no wildcard prod fallback. |
| `backend/main.py` | Modify | Use configured CORS origins and stop logging static AWS keys as required runtime. |
| `backend/app/s3_client.py` | Modify | Create boto3 S3 client with region only unless explicit local credentials are supplied. |
| `evaluation/harness/s3_upload.py`, `evaluation/storage.py`, `evaluation/s3_client.py` | Modify | Accept AWS default credential chain/OIDC env credentials. |
| `.env.example` | Modify | Document local credentials as optional; deployed runtime uses IAM/SSM/secrets. |

## Interfaces / Contracts

Terraform service inputs include `service_name`, `environment`, `image_tag`, `container_port`, `public_hostnames`, `domain_name`, `local_origin_url`, `secret_arns`, `ssm_params`, `task_role_policy_json`, `expiration_at`. `DOMAIN_NAME` defaults to `artesolutions.com.co` but remains variable-driven. Backend env adds `ALLOWED_CORS_ORIGINS` as comma-separated origins; prod requires explicit Cloudflare frontend/admin/staging origins and rejects `*`.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| IaC | Module syntax, staging/prod validation, sensitive outputs | `terraform fmt -check`, `validate`, plan fixtures for prod and local-staging. |
| Backend | CORS allowlist and wildcard-prod failure | FastAPI/Pydantic tests around `ALLOWED_CORS_ORIGINS` and env mode. |
| AWS auth | S3 clients use default provider chain without static keys | Mock `boto3.client` to assert no key args when absent; keep explicit local key tests. |
| CI/CD | PR skips prod deploy; main deploys changed services | Workflow tests/lint with mocked events or action dry-run where practical. |

## Migration / Rollout

No data migration. Roll out by creating ECR/roles/secrets first, then ECS services with health checks, then Cloudflare hostnames. Rollback uses previous task definition/image tag and revokes replaced tunnel tokens.

## Open Questions

- [ ] Cloudflare zone id and token storage path.
