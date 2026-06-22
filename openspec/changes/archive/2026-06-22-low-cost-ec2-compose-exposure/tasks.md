# Tasks: Low-Cost EC2 Compose Exposure

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 800-1,150 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 to tracker → PR 2 to PR 1 branch → PR 3 to PR 2 branch |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | EC2 Compose module | PR 1 | Base = feature/tracker branch; module/templates/checks; no cutover. |
| 2 | Prod Terraform wiring | PR 2 | Base = PR 1 branch; AMI, hostnames, tunnel wiring. |
| 3 | CI deploy/evidence | PR 3 | Base = PR 2 branch; SSM deploy, secrets, verification. |

## Phase 1: Module Foundation

- [x] 1.1 Add checks for `docker-compose.yml.tftpl`: Compose DNS origins, no public app port publishing.
- [x] 1.2 Add checks for `deploy.sh.tftpl`: `<sha-tag>`, previous tag, failing pull/compose/health exits.
- [x] 1.3 Create `infra/terraform/modules/ec2_compose_host/{variables.tf,outputs.tf}` for subnet, optional `ami_id_override`, size, images, URLs, bucket, secrets, tunnel token, deploy metadata.
- [x] 1.4 Create `infra/terraform/modules/ec2_compose_host/main.tf` with EC2, outbound-only SG, instance profile, SSM/ECR/S3/secrets IAM, bootstrap.
- [x] 1.5 Create `docker-compose.yml.tftpl` and `deploy.sh.tftpl`; keep secrets out of outputs.

## Phase 2: Production Infrastructure Wiring

- [x] 2.1 Add `data.aws_ami.ubuntu_lts` in `infra/terraform/envs/prod/main.tf` with Canonical owner, HVM/EBS filters, Ubuntu LTS pattern, `most_recent = true`.
- [x] 2.2 Resolve image from `ami_id_override` or `data.aws_ami.ubuntu_lts.id`; commit no fixed AMI IDs.
- [x] 2.3 Add sensitive `backend_hostname`, `frontend_hostname`, `admin_hostname` in `infra/terraform/envs/prod/variables.tf` with no defaults.
- [x] 2.4 Wire hostnames into Cloudflare routes/DNS, public URLs, CORS origins, UI API URL; remove hardcoded hostname defaults/labels.
- [x] 2.5 Update `infra/terraform/modules/cloudflare_tunnel/*` for central connector mode with Compose DNS origins and retained non-production sidecar support.
- [x] 2.6 Replace ECS/per-service production tunnels in `infra/terraform/envs/prod/main.tf` with one `edge_tunnel` plus `ec2_compose_host`.
- [x] 2.7 Update `infra/terraform/envs/prod/{variables.tf,outputs.tf}` for EC2 inputs, one tunnel secret, runtime secret refs, sensitive derived outputs, backend env map default `{}`.
- [x] 2.8 Update `infra/terraform/modules/github_oidc/*` from ECS/pass-role permissions to scoped SSM Run Command/status reads.

## Phase 3: CI Deployment Flow

- [x] 3.1 Add workflow checks for `.github/workflows/ci.yml`: PRs never deploy; `main` deploys after CI, health, evaluation gates.
- [x] 3.2 Pass `TF_VAR_backend_hostname`, `TF_VAR_frontend_hostname`, `TF_VAR_admin_hostname` from GitHub Secrets/equivalent; no workflow hardcoding.
- [x] 3.3 Pass `TF_VAR_backend_runtime_environment_variables: ${{ vars.PROD_BACKEND_RUNTIME_ENV_JSON || '{}' }}` and keep secrets in ARNs/Secrets Manager/SSM.
- [x] 3.4 Keep SHA-tagged ECR promotion and invoke `/opt/arte-chatbot/deploy.sh sha-${{ github.sha }}` through SSM; remove ECS deploy paths.

## Phase 4: Verification and Setup Evidence

- [x] 4.1 Run `terraform -chdir=infra/terraform/envs/prod fmt -recursive` and `terraform -chdir=infra/terraform/envs/prod validate`.
- [x] 4.2 Verify plan evidence: Ubuntu LTS AMI data source selected by default, override works, no fixed AMI ID required.
- [x] 4.3 Verify hostname evidence: no repo/IaC defaults for service hostnames; Cloudflare DNS may become public.
- [x] 4.4 Verify runtime/deploy evidence: env map, SSM instance, `docker compose ps`, Cloudflare health, rollback to Fargate.
