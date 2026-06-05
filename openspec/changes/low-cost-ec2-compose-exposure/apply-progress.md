# Apply Progress: Low-Cost EC2 Compose Exposure

## Status

- Change: `low-cost-ec2-compose-exposure`
- Delivery mode: chained PR slice
- Chain strategy: `feature-branch-chain`
- Current work unit: Unit 1 — EC2 Compose module
- PR boundary: PR #1 targets the feature/tracker branch; this slice adds only the reusable EC2 Compose module, templates, and static checks. Production cutover/wiring and CI deploy remain out of scope.
- Mode: Strict TDD

## Completed Tasks

- [x] 1.1 Add checks for `docker-compose.yml.tftpl`: Compose DNS origins, no public app port publishing.
- [x] 1.2 Add checks for `deploy.sh.tftpl`: `<sha-tag>`, previous tag, failing pull/compose/health exits.
- [x] 1.3 Create `infra/terraform/modules/ec2_compose_host/{variables.tf,outputs.tf}` for subnet, optional `ami_id_override`, size, images, URLs, bucket, secrets, tunnel token, deploy metadata.
- [x] 1.4 Create `infra/terraform/modules/ec2_compose_host/main.tf` with EC2, outbound-only SG, instance profile, SSM/ECR/S3/secrets IAM, bootstrap.
- [x] 1.5 Create `docker-compose.yml.tftpl` and `deploy.sh.tftpl`; keep secrets out of outputs.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `scripts/tests/test_ec2_compose_module_checks.py` | Static/unit | N/A (new module/templates) | ✅ `uv run pytest scripts/tests/test_ec2_compose_module_checks.py` failed with `ModuleNotFoundError: No module named 'ec2_compose_module_checks'` before implementation | ✅ `3 passed` after adding checks and templates | ✅ Covered service presence, Compose DNS origins, no app `ports`, and 404 fallback | ✅ `terraform fmt -recursive`; tests still `3 passed` |
| 1.2 | `scripts/tests/test_ec2_compose_module_checks.py` | Static/unit | N/A (new deploy template) | ✅ Same RED import failure before implementation | ✅ Deploy checks passed after adding `deploy.sh.tftpl` | ✅ Covered SHA tag guard, previous/current tag metadata, and fail-fast pull/compose/health commands | ✅ `terraform fmt -recursive`; tests still `3 passed` |
| 1.3 | `scripts/tests/test_ec2_compose_module_checks.py` | Static/unit | N/A (new Terraform module) | ✅ Same RED import failure before implementation | ✅ Module contract checks passed after adding `variables.tf` and `outputs.tf` | ✅ Covered required inputs plus non-secret outputs and no tunnel token output | ✅ `terraform fmt -recursive`; tests still `3 passed` |
| 1.4 | `scripts/tests/test_ec2_compose_module_checks.py` | Static/unit | N/A (new Terraform module) | ✅ Same RED import failure before implementation | ✅ Host checks passed after adding `main.tf` | ✅ Covered outbound-only SG, SSM/ECR/S3/secrets IAM, and `/opt/arte-chatbot` bootstrap assets | ✅ `terraform validate` succeeded after `terraform init -backend=false` |
| 1.5 | `scripts/tests/test_ec2_compose_module_checks.py` | Static/unit | N/A (new templates) | ✅ Same RED import failure before implementation | ✅ Template checks passed after adding Compose and deploy templates | ✅ Covered internal service exposure, runtime env file, Cloudflare token env, SHA deploy, rollback metadata, and backend health check | ✅ `terraform fmt -recursive`; tests still `3 passed` |

## Validation Results

| Command | Result | Notes |
|---------|--------|-------|
| `uv run pytest scripts/tests/test_ec2_compose_module_checks.py` | ✅ Pass | 3 tests passed. |
| `terraform -chdir=infra/terraform/modules/ec2_compose_host fmt -recursive` | ✅ Pass | Formatted new module files. |
| `terraform -chdir=infra/terraform/modules/ec2_compose_host init -backend=false && terraform -chdir=infra/terraform/modules/ec2_compose_host validate` | ✅ Pass | Validated the standalone module after provider init; `.terraform/` cache was removed after validation. |

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `scripts/tests/test_ec2_compose_module_checks.py` | Created | Added strict-TDD static tests for the first EC2 Compose module slice. |
| `scripts/ec2_compose_module_checks.py` | Created | Added repository-only validation for Compose template, deploy template, and module contract. |
| `infra/terraform/modules/ec2_compose_host/variables.tf` | Created | Declared EC2 host, image, URL, bucket, runtime env, secret, and deploy inputs. |
| `infra/terraform/modules/ec2_compose_host/outputs.tf` | Created | Exposed host/deploy metadata without exposing tunnel token or secret values. |
| `infra/terraform/modules/ec2_compose_host/main.tf` | Created | Added EC2 instance, outbound-only SG, instance profile, SSM/ECR/S3/secrets IAM, and bootstrap rendering for Compose assets. |
| `infra/terraform/modules/ec2_compose_host/templates/docker-compose.yml.tftpl` | Created | Added backend, frontend, admin, and cloudflared services using internal Compose exposure and DNS-origin contract values. |
| `infra/terraform/modules/ec2_compose_host/templates/deploy.sh.tftpl` | Created | Added SHA-tag deploy script with ECR login, runtime secret resolution, previous/current tag metadata, Compose restart, and backend health check. |
| `openspec/changes/low-cost-ec2-compose-exposure/tasks.md` | Updated | Marked Phase 1 tasks complete only. |
| `openspec/changes/low-cost-ec2-compose-exposure/apply-progress.md` | Created | Recorded cumulative slice progress and TDD cycle evidence. |

## Deviations and Limitations

- No deviation from the selected first work unit boundary: production Terraform wiring, central tunnel resource replacement, GitHub OIDC changes, and CI deploy remain untouched.
- The standalone module validates syntactically, but it is not yet called by `infra/terraform/envs/prod`; production plan evidence belongs to Unit 2.
- Runtime secret resolution is implemented in the deploy template using AWS CLI calls so secrets remain out of Terraform outputs and committed files.

## Remaining Tasks

- [ ] 2.1 Add `data.aws_ami.ubuntu_lts` in `infra/terraform/envs/prod/main.tf` with Canonical owner, HVM/EBS filters, Ubuntu LTS pattern, `most_recent = true`.
- [ ] 2.2 Resolve image from `ami_id_override` or `data.aws_ami.ubuntu_lts.id`; commit no fixed AMI IDs.
- [ ] 2.3 Add sensitive `backend_hostname`, `frontend_hostname`, `admin_hostname` in `infra/terraform/envs/prod/variables.tf` with no defaults.
- [ ] 2.4 Wire hostnames into Cloudflare routes/DNS, public URLs, CORS origins, UI API URL; remove hardcoded hostname defaults/labels.
- [ ] 2.5 Update `infra/terraform/modules/cloudflare_tunnel/*` for central connector mode with Compose DNS origins and retained non-production sidecar support.
- [ ] 2.6 Replace ECS/per-service production tunnels in `infra/terraform/envs/prod/main.tf` with one `edge_tunnel` plus `ec2_compose_host`.
- [ ] 2.7 Update `infra/terraform/envs/prod/{variables.tf,outputs.tf}` for EC2 inputs, one tunnel secret, runtime secret refs, sensitive derived outputs, backend env map default `{}`.
- [ ] 2.8 Update `infra/terraform/modules/github_oidc/*` from ECS/pass-role permissions to scoped SSM Run Command/status reads.
- [ ] Phase 3 CI deployment flow tasks.
- [ ] Phase 4 verification and setup evidence tasks.
