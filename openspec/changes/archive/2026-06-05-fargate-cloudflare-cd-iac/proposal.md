# Proposal: Fargate Cloudflare CD IaC

## Intent

Make Arte Chatbot deployable with repeatable Fargate + Cloudflare Tunnel IaC/CD, without adding an ALB.

## Scope

### In Scope
- Terraform/IaC for ECR, ECS Fargate, IAM, logs, SSM/Secrets Manager, Cloudflare tunnel/DNS.
- v1 ingress: `backend + cloudflared -> localhost:8000`; `frontend/admin + cloudflared -> localhost:3000`.
- Separate tunnel scope per service/hostname group unless all connectors reach all origins.
- ECR promotion after CI/evaluation; prod deploy only from merge/push to `main`.
- Local-only staging isolated from CI/prod by names, state, tunnel tokens, and params.
- Extensible service layout for future admin panel and Chatwoot.

### Out of Scope
- EC2 except as fallback.
- S3 + CloudFront frontend hosting; defer until UI stabilizes.
- Broad production code rewrites.

## Capabilities

### New Capabilities
- `fargate-cloudflare-ingress`: Fargate services expose private origins through scoped Cloudflare Tunnel sidecars.
- `ecs-runtime-configuration`: Runtime config/secrets use task roles, execution roles, SSM, and Secrets Manager.
- `ecr-cd-promotion`: CI gates image promotion and deploys prod only from `main`.
- `local-staging-isolation`: Staging cannot reuse prod state, names, tokens, or params.

### Modified Capabilities
None

## Approach

Use Fargate-first IaC/CD. Keep backend and frontend/admin containerized for v1. Each exposed service owns its origin and same-task `cloudflared` connector over `localhost`, avoiding shared-tunnel misrouting. Task role grants S3 access; execution role handles images, logs, and secret injection.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `infra/` or `deploy/` | New | Terraform for AWS and Cloudflare. |
| `.github/workflows/ci.yml` | Modified | ECR promotion and main-only deploy. |
| `.env.example` | Modified | Role-based AWS auth and runtime config/secrets. |
| `backend/app/config.py`, `backend/main.py` | Modified | Deployed CORS/public URLs. |
| `backend/app/s3_client.py`, `evaluation/harness/s3_upload.py` | Modified | Default AWS credential chain when static keys are absent. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Shared tunnel routes to absent localhost origin | High | Separate tunnel scopes. |
| Missing outbound egress | Medium | Specify NAT/VPC endpoint needs in design. |
| Prod/staging mix-up | Medium | Separate names, state, tokens, and parameter paths. |

## Rollback Plan

Revert workflow/IaC changes, redeploy the previous ECR image/task definition, and revoke new Cloudflare tunnel tokens. Destroy local staging independently.

## Dependencies

- AWS OIDC, ECR, ECS, IAM, logs, SSM/Secrets Manager, S3.
- Cloudflare Tunnel/DNS API token.

## Success Criteria

- [ ] PRs build, health-check, and evaluate without deploying prod.
- [ ] `main` promotes images and updates ECS services.
- [ ] Backend and frontend/admin work through Cloudflare hostnames.
- [ ] Runtime S3 access works through ECS task role without static AWS keys.
- [ ] Local staging uses isolated state, names, tokens, and params.
