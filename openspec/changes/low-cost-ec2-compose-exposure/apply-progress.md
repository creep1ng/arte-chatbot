# Apply Progress: Low-Cost EC2 Compose Exposure

## Status

- Change: `low-cost-ec2-compose-exposure`
- Delivery mode: chained PR slice
- Chain strategy: `feature-branch-chain`
- Current work unit: Unit 2 — Production Terraform wiring
- PR boundary: PR #2 targets the Unit 1 branch; this slice wires the reusable EC2 Compose module into `infra/terraform/envs/prod`, replaces production per-service ECS/tunnel wiring with one central tunnel, and updates Terraform-only deploy role permissions. GitHub Actions/SSM deploy workflow remains out of scope for Unit 3.
- Mode: Strict TDD

## Completed Tasks

- [x] 1.1 Add checks for `docker-compose.yml.tftpl`: Compose DNS origins, no public app port publishing.
- [x] 1.2 Add checks for `deploy.sh.tftpl`: `<sha-tag>`, previous tag, failing pull/compose/health exits.
- [x] 1.3 Create `infra/terraform/modules/ec2_compose_host/{variables.tf,outputs.tf}` for subnet, optional `ami_id_override`, size, images, URLs, bucket, secrets, tunnel token, deploy metadata.
- [x] 1.4 Create `infra/terraform/modules/ec2_compose_host/main.tf` with EC2, outbound-only SG, instance profile, SSM/ECR/S3/secrets IAM, bootstrap.
- [x] 1.5 Create `docker-compose.yml.tftpl` and `deploy.sh.tftpl`; keep secrets out of outputs.
- [x] 2.1 Add `data.aws_ami.ubuntu_lts` in `infra/terraform/envs/prod/main.tf` with Canonical owner, HVM/EBS filters, Ubuntu LTS pattern, `most_recent = true`.
- [x] 2.2 Resolve image from `ami_id_override` or `data.aws_ami.ubuntu_lts.id`; commit no fixed AMI IDs.
- [x] 2.3 Add sensitive `backend_hostname`, `frontend_hostname`, `admin_hostname` in `infra/terraform/envs/prod/variables.tf` with no defaults.
- [x] 2.4 Wire hostnames into Cloudflare routes/DNS, public URLs, CORS origins, UI API URL; remove hardcoded hostname defaults/labels.
- [x] 2.5 Update `infra/terraform/modules/cloudflare_tunnel/*` for central connector mode with Compose DNS origins and retained non-production sidecar support.
- [x] 2.6 Replace ECS/per-service production tunnels in `infra/terraform/envs/prod/main.tf` with one `edge_tunnel` plus `ec2_compose_host`.
- [x] 2.7 Update `infra/terraform/envs/prod/{variables.tf,outputs.tf}` for EC2 inputs, one tunnel secret, runtime secret refs, sensitive derived outputs, backend env map default `{}`.
- [x] 2.8 Update `infra/terraform/modules/github_oidc/*` from ECS/pass-role permissions to scoped SSM Run Command/status reads.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `scripts/tests/test_ec2_compose_module_checks.py` | Static/unit | N/A (new module/templates) | ✅ `uv run pytest scripts/tests/test_ec2_compose_module_checks.py` failed with `ModuleNotFoundError: No module named 'ec2_compose_module_checks'` before implementation | ✅ `3 passed` after adding checks and templates | ✅ Covered service presence, Compose DNS origins, no app `ports`, and 404 fallback | ✅ `terraform fmt -recursive`; tests still `3 passed` |
| 1.2 | `scripts/tests/test_ec2_compose_module_checks.py` | Static/unit | N/A (new deploy template) | ✅ Same RED import failure before implementation | ✅ Deploy checks passed after adding `deploy.sh.tftpl` | ✅ Covered SHA tag guard, previous/current tag metadata, and fail-fast pull/compose/health commands | ✅ `terraform fmt -recursive`; tests still `3 passed` |
| 1.3 | `scripts/tests/test_ec2_compose_module_checks.py` | Static/unit | N/A (new Terraform module) | ✅ Same RED import failure before implementation | ✅ Module contract checks passed after adding `variables.tf` and `outputs.tf` | ✅ Covered required inputs plus non-secret outputs and no tunnel token output | ✅ `terraform fmt -recursive`; tests still `3 passed` |
| 1.4 | `scripts/tests/test_ec2_compose_module_checks.py` | Static/unit | N/A (new Terraform module) | ✅ Same RED import failure before implementation | ✅ Host checks passed after adding `main.tf` | ✅ Covered outbound-only SG, SSM/ECR/S3/secrets IAM, and `/opt/arte-chatbot` bootstrap assets | ✅ `terraform validate` succeeded after `terraform init -backend=false` |
| 1.5 | `scripts/tests/test_ec2_compose_module_checks.py` | Static/unit | N/A (new templates) | ✅ Same RED import failure before implementation | ✅ Template checks passed after adding Compose and deploy templates | ✅ Covered internal service exposure, runtime env file, Cloudflare token env, SHA deploy, rollback metadata, and backend health check | ✅ `terraform fmt -recursive`; tests still `3 passed` |
| 2.1 | `scripts/tests/test_prod_terraform_wiring_checks.py` | Static/unit | ✅ `uv run pytest scripts/tests/test_ec2_compose_module_checks.py scripts/tests/test_terraform_foundation.py` → `8 passed` before edits | ✅ New prod wiring test failed with `ModuleNotFoundError: No module named 'prod_terraform_wiring_checks'` before production wiring | ✅ `uv run pytest scripts/tests/test_prod_terraform_wiring_checks.py` → `3 passed` after adding checker and AMI data source | ✅ Covered Canonical owner, HVM/EBS filters, Ubuntu LTS name pattern, and `most_recent = true` | ✅ `terraform fmt`; relevant tests still passed |
| 2.2 | `scripts/tests/test_prod_terraform_wiring_checks.py` | Static/unit | ✅ Same safety net as 2.1 | ✅ Same RED import failure before implementation | ✅ AMI resolution check passed after `local.compose_host_ami_id = coalesce(var.ami_id_override, data.aws_ami.ubuntu_lts.id)` and no fixed AMI default | ✅ Covered default data-source path plus emergency override variable | ✅ `terraform validate` passed |
| 2.3 | `scripts/tests/test_prod_terraform_wiring_checks.py` | Static/unit | ✅ Same safety net as 2.1 | ✅ Same RED import failure before implementation | ✅ Hostname input checks passed after adding sensitive hostname variables without defaults | ✅ Covered backend, frontend, and admin hostname variables plus absence of defaults | ✅ Existing `terraform_foundation_checks.py` was updated to match the new external-hostname contract |
| 2.4 | `scripts/tests/test_prod_terraform_wiring_checks.py` | Static/unit | ✅ Same safety net as 2.1 | ✅ Same RED import failure before implementation | ✅ Hostname wiring checks passed after Terraform derived URLs/CORS from sensitive hostname inputs | ✅ Covered Cloudflare routes, public URLs, CORS origins, and UI API URL inputs | ✅ `terraform fmt`; relevant tests still passed |
| 2.5 | `scripts/tests/test_prod_terraform_wiring_checks.py` and `scripts/tests/test_terraform_foundation.py` | Static/unit | ✅ Same safety net as 2.1 | ✅ Tests initially rejected missing central connector/Compose DNS wiring | ✅ Cloudflare tunnel checks passed with `central_connector_mode = true` and generic token output wording | ✅ Covered mixed-origin guard retention and central-mode enablement for production | ✅ Existing foundation checks now assert central connector behavior instead of obsolete per-service sidecars |
| 2.6 | `scripts/tests/test_prod_terraform_wiring_checks.py` | Static/unit | ✅ Same safety net as 2.1 | ✅ Tests initially rejected missing one-tunnel/Compose-host production wiring | ✅ Prod root check passed after replacing ECS/per-service tunnel modules with one `edge_tunnel` and `compose_host` | ✅ Covered no per-service production tunnel module names and all three Compose DNS origins | ✅ `terraform validate` passed |
| 2.7 | `scripts/tests/test_prod_terraform_wiring_checks.py` | Static/unit | ✅ Same safety net as 2.1 | ✅ Tests initially rejected missing EC2 variables/outputs/runtime env map | ✅ Prod variables/outputs checks passed after adding EC2 inputs, one tunnel secret, env map default `{}`, runtime secret refs, and sensitive derived outputs | ✅ Covered host metadata outputs and removal of obsolete ECS service outputs | ✅ `terraform fmt`; relevant tests still passed |
| 2.8 | `scripts/tests/test_prod_terraform_wiring_checks.py` | Static/unit | ✅ Same safety net as 2.1 | ✅ Tests initially rejected ECS/pass-role deploy permissions | ✅ OIDC checks passed after replacing ECS/pass-role variables with scoped SSM `SendCommand`/status-read permissions | ✅ Covered SSM instance/document ARNs and absence of ECS/pass-role strings | ✅ `terraform validate` passed |

## Validation Results

| Command | Result | Notes |
|---------|--------|-------|
| `uv run pytest scripts/tests/test_ec2_compose_module_checks.py scripts/tests/test_terraform_foundation.py` | ✅ Pass | Safety net before Unit 2 edits: 8 tests passed. |
| `uv run pytest scripts/tests/test_prod_terraform_wiring_checks.py` | ✅ Pass | RED first failed with missing checker module; GREEN completed with 3 tests passed. |
| `terraform -chdir=infra/terraform/envs/prod fmt -recursive && terraform -chdir=infra/terraform/modules/github_oidc fmt -recursive && terraform -chdir=infra/terraform/modules/cloudflare_tunnel fmt -recursive` | ✅ Pass | Formatted production root and modified modules. |
| `uv run pytest scripts/tests/test_prod_terraform_wiring_checks.py scripts/tests/test_ec2_compose_module_checks.py scripts/tests/test_terraform_foundation.py` | ✅ Pass | 11 relevant static/unit tests passed after implementation and refactor. |
| `terraform -chdir=infra/terraform/envs/prod init -backend=false` | ✅ Pass | Providers/modules initialized without touching remote backend. |
| `terraform -chdir=infra/terraform/envs/prod validate` | ✅ Pass | Production Terraform configuration is valid. |

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `scripts/tests/test_ec2_compose_module_checks.py` | Created in Unit 1 | Added strict-TDD static tests for the first EC2 Compose module slice. |
| `scripts/ec2_compose_module_checks.py` | Created in Unit 1 | Added repository-only validation for Compose template, deploy template, and module contract. |
| `infra/terraform/modules/ec2_compose_host/variables.tf` | Created in Unit 1 | Declared EC2 host, image, URL, bucket, runtime env, secret, and deploy inputs. |
| `infra/terraform/modules/ec2_compose_host/outputs.tf` | Created in Unit 1 | Exposed host/deploy metadata without exposing tunnel token or secret values. |
| `infra/terraform/modules/ec2_compose_host/main.tf` | Created in Unit 1 | Added EC2 instance, outbound-only SG, instance profile, SSM/ECR/S3/secrets IAM, and bootstrap rendering for Compose assets. |
| `infra/terraform/modules/ec2_compose_host/templates/docker-compose.yml.tftpl` | Created in Unit 1 | Added backend, frontend, admin, and cloudflared services using internal Compose exposure and DNS-origin contract values. |
| `infra/terraform/modules/ec2_compose_host/templates/deploy.sh.tftpl` | Created in Unit 1 | Added SHA-tag deploy script with ECR login, runtime secret resolution, previous/current tag metadata, Compose restart, and backend health check. |
| `scripts/tests/test_prod_terraform_wiring_checks.py` | Created | Added strict-TDD static tests for production AMI, hostname, tunnel, EC2 host, outputs, and SSM deploy-role wiring. |
| `scripts/prod_terraform_wiring_checks.py` | Created | Added repository-only validation for Unit 2 production Terraform wiring. |
| `infra/terraform/envs/prod/main.tf` | Modified | Replaced production ECS services/per-service tunnels with latest Ubuntu LTS data source, one central Cloudflare tunnel, SSM-stored tunnel token, EC2 Compose host module, and SSM-scoped OIDC inputs. |
| `infra/terraform/envs/prod/variables.tf` | Modified | Replaced Fargate/per-service tunnel inputs with EC2 host inputs, optional AMI override, sensitive hostname variables, one tunnel secret, env map default `{}`, runtime secret refs, and KMS key refs. |
| `infra/terraform/envs/prod/outputs.tf` | Modified | Replaced ECS outputs with EC2 host/deploy metadata and sensitive hostname-derived public URL/tunnel outputs. |
| `infra/terraform/modules/cloudflare_tunnel/outputs.tf` | Modified | Updated tunnel-token wording from ECS sidecar to generic runtime secret injection. |
| `infra/terraform/modules/github_oidc/main.tf` | Modified | Replaced ECS deploy/pass-role policy statements with scoped SSM Run Command and status-read permissions. |
| `infra/terraform/modules/github_oidc/variables.tf` | Modified | Replaced ECS/pass-role variables with SSM instance/document ARN variables. |
| `scripts/terraform_foundation_checks.py` | Modified | Updated existing Terraform foundation static checks for the new central tunnel/external hostname contract. |
| `scripts/tests/test_terraform_foundation.py` | Modified | Updated foundation tests to assert central tunnel and external hostname behavior instead of obsolete per-service Fargate sidecars. |
| `openspec/changes/low-cost-ec2-compose-exposure/tasks.md` | Updated | Marked Phase 2 tasks complete only. |
| `openspec/changes/low-cost-ec2-compose-exposure/apply-progress.md` | Updated | Recorded cumulative Unit 1 + Unit 2 progress and TDD cycle evidence. |

## Deviations and Limitations

- No deviation from the selected Unit 2 boundary: GitHub Actions workflow deploy changes and live EC2/Cloudflare verification remain out of scope for Unit 3/Phase 4.
- `terraform validate` proves syntax/module wiring only; no `terraform plan/apply` was run because production credentials, sensitive hostname inputs, and tunnel secret values are intentionally not present in the workspace.
- Review-budget risk remains high because replacing the production root necessarily removes the old ECS/per-service tunnel wiring; this slice is still focused on one autonomous PR boundary.

## Remaining Tasks

- [ ] Phase 3 CI deployment flow tasks.
- [ ] Phase 4 verification and setup evidence tasks.
