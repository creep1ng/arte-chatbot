# Verification Report: Low-Cost EC2 Compose Exposure

**Change**: `low-cost-ec2-compose-exposure`
**Mode**: Strict TDD (`uv run pytest`)
**Artifact store**: OpenSpec
**Verdict**: PASS WITH WARNINGS

## Executive Summary

Local verification passed for the EC2 Compose production exposure change. The OpenSpec artifacts, implementation files, strict-TDD evidence, static/unit verification suite, and Terraform validation are coherent with the intended low-cost EC2 + Cloudflare Tunnel design.

Warnings remain because live production proof was not available in this workspace: AWS/Cloudflare credentials, Terraform plan/apply against real production, SSM Run Command, `docker compose ps`, public Cloudflare URL checks, and rollback execution could not be performed.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 21 |
| Tasks complete | 21 |
| Tasks incomplete | 0 |
| Apply progress present | Yes |
| Proposal/design/specs present | Yes |

## Build & Tests Execution

### Required pytest suite

**Result**: Passed

```text
Command: uv run pytest scripts/tests/test_phase4_verification_checks.py scripts/tests/test_workflow_deploy_checks.py scripts/tests/test_prod_terraform_wiring_checks.py scripts/tests/test_ec2_compose_module_checks.py scripts/tests/test_terraform_foundation.py scripts/tests/test_cd_and_staging_guards.py
Result: 25 passed in 0.08s
```

### Terraform validation

**Production root**: Passed

```text
Command: terraform -chdir=infra/terraform/envs/prod fmt -check -recursive && terraform -chdir=infra/terraform/envs/prod validate
Result: Success! The configuration is valid.
```

**Modified modules**: Passed after local provider init

```text
Command: terraform -chdir=infra/terraform/modules/ec2_compose_host init -backend=false -no-color && terraform -chdir=infra/terraform/modules/ec2_compose_host validate -no-color
Result: Success! The configuration is valid.

Command: terraform -chdir=infra/terraform/modules/cloudflare_tunnel init -backend=false -no-color && terraform -chdir=infra/terraform/modules/cloudflare_tunnel validate -no-color
Result: Success! The configuration is valid.

Command: terraform -chdir=infra/terraform/modules/github_oidc init -backend=false -no-color && terraform -chdir=infra/terraform/modules/github_oidc validate -no-color
Result: Success! The configuration is valid.
```

**Module formatting**: Passed

```text
Command: terraform -chdir=infra/terraform/modules/ec2_compose_host fmt -check -recursive && terraform -chdir=infra/terraform/modules/cloudflare_tunnel fmt -check -recursive && terraform -chdir=infra/terraform/modules/github_oidc fmt -check -recursive
Result: passed with no output
```

### Coverage

Coverage analysis skipped: `pytest-cov` is not installed in the project environment.

```text
Command: uv run pytest --cov=scripts --cov-report=term-missing ...
Result: pytest: error: unrecognized arguments: --cov=scripts --cov-report=term-missing
```

## Strict TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `apply-progress.md` contains a TDD Cycle Evidence table. |
| All tasks have tests | ✅ | 21/21 tasks list test evidence. |
| RED confirmed | ✅ | Reported test files exist and were read. Historical RED output is recorded in apply-progress. |
| GREEN confirmed | ✅ | Required suite passed now: 25 tests. |
| Triangulation adequate | ✅ | Multiple static checks cover AMI, hostname, tunnel, deploy, rollback metadata, and guard behavior. |
| Safety net for modified files | ✅ | Apply-progress records safety-net runs before later-phase edits. |

**TDD Compliance**: 6/6 checks passed.

## Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Static/unit | 25 | 6 | pytest |
| Integration | 0 | 0 | Not exercised locally |
| E2E/live | 0 | 0 | Unavailable without production AWS/Cloudflare |
| **Total** | **25** | **6** | |

## Assertion Quality

**Assertion quality**: ✅ All reviewed assertions call repository check functions or scripts and assert concrete behavior/finding absence. No tautologies, ghost loops, smoke-only assertions, or type-only assertions were found in the relevant test files.

## Spec Compliance Matrix

| Requirement / Scenario group | Covering evidence | Result |
|---|---|---|
| Latest Ubuntu LTS AMI discovery | `test_prod_uses_dynamic_ubuntu_lts_ami_without_fixed_ami_defaults`, `test_phase4_records_ami_and_hostname_policy_evidence`; `infra/terraform/envs/prod/main.tf` data source | ✅ COMPLIANT locally |
| External service hostname inputs / DNS visibility | `test_prod_externalizes_hostnames_and_routes_single_central_tunnel`, `test_phase4_records_ami_and_hostname_policy_evidence`; sensitive variables with no defaults | ✅ COMPLIANT locally |
| One production Compose tunnel exposure | `test_compose_template_uses_internal_dns_without_public_ports`, `test_prod_uses_central_cloudflare_tunnel_and_compose_origins`; one `edge_tunnel` with Compose DNS origins | ✅ COMPLIANT locally / ⚠️ live routing unverified |
| Direct app port access blocked | `test_compose_template_uses_internal_dns_without_public_ports`, `test_module_declares_host_inputs_outputs_and_outbound_only_security`; no app `ports`, no SG ingress | ✅ COMPLIANT locally / ⚠️ live network unverified |
| Compose DNS origins and fallback | `test_compose_template_uses_internal_dns_without_public_ports`; tunnel module adds `http_status:404` fallback | ✅ COMPLIANT locally |
| Accepted single-host tradeoff / rollback path | `test_deploy_template_requires_sha_tags_and_safe_rollback_metadata`, apply-progress rollback limitation notes | ⚠️ PARTIAL: metadata exists; live rollback execution unverified |
| Hostname pass-through in workflow | `test_workflow_passes_external_hostnames_and_runtime_env_without_hardcoding` | ✅ COMPLIANT locally |
| Backend runtime config pass-through | `test_workflow_passes_external_hostnames_and_runtime_env_without_hardcoding`, `test_phase4_records_runtime_deploy_and_rollback_evidence`; Terraform map default `{}` | ✅ COMPLIANT locally |
| CI/evaluation gate before promotion | `test_workflow_keeps_production_deploys_on_main_after_ci_health_and_evaluation`, `test_workflow_builds_all_images_and_pushes_sha_candidate_tags_after_gates` | ✅ COMPLIANT locally |
| Main-only production deploy | `test_workflow_keeps_production_deploys_on_main_after_ci_health_and_evaluation` | ✅ COMPLIANT locally |
| SHA image deploy and rollback metadata | `test_workflow_uses_sha_ecr_tags_and_ssm_compose_deploy_instead_of_ecs`, deploy template review | ✅ COMPLIANT locally |
| OIDC / scoped deploy permissions | `test_prod_wires_ec2_compose_runtime_outputs_and_ssm_deploy_permissions`; `github_oidc` SSM permissions | ✅ COMPLIANT locally |
| Runtime S3 access via role, no static AWS keys | `test_module_declares_host_inputs_outputs_and_outbound_only_security`; IAM role includes S3 access and Compose env does not set static AWS keys | ✅ COMPLIANT locally / ⚠️ live S3 access unverified |
| Secrets from Secrets Manager/SSM | deploy template `resolve_secret`; runtime secret ARNs | ✅ COMPLIANT locally / ⚠️ live secret retrieval unverified |
| Configured CORS origins and runtime URLs | Terraform locals and module inputs derive URLs/origins from hostname variables | ✅ COMPLIANT locally / ⚠️ browser CORS unverified |
| Production no longer uses localhost sidecars | prod tunnel origins are `backend/frontend/admin` Compose DNS; no ECS deploy path in workflow | ✅ COMPLIANT locally |
| Retained non-production sidecar behavior | Cloudflare module preserves `central_connector_mode=false` validation for single origin mode | ✅ COMPLIANT locally |
| Terraform-managed Cloudflare routes and token secrecy | Cloudflare tunnel resources/DNS records managed; tunnel token output sensitive and stored through SSM secret module | ✅ COMPLIANT locally / ⚠️ live Cloudflare apply unverified |

**Compliance summary**: Local/static requirements pass. Live runtime scenarios are partially verified by source and Terraform validation only.

## Correctness / Static Evidence

| Area | Status | Evidence |
|------|--------|----------|
| EC2 Compose module | ✅ | EC2 instance, outbound-only SG, IAM role, user data, Compose/deploy templates exist. |
| Production AMI | ✅ | Canonical Ubuntu LTS `aws_ami` with `most_recent = true`; optional `ami_id_override`. |
| Hostname handling | ✅ | `backend_hostname`, `frontend_hostname`, `admin_hostname` are sensitive variables with no defaults. |
| Cloudflare Tunnel | ✅ | One central tunnel routes to `http://backend:8000`, `http://frontend:3000`, `http://admin:3000`. |
| CI/CD deploy | ✅ | Main-only deploy, SHA tags, Terraform apply, SSM Run Command, backend Cloudflare health check. |
| Secrets/config | ✅ | Secrets referenced by ARNs; non-secret runtime config uses `map(string)` and GitHub Variable fallback. |
| Rollback metadata | ✅ | `previous-image-tag` and `current-image-tag` files maintained by deploy script. |

## Design Coherence

| Design decision | Followed? | Notes |
|---|---:|---|
| One Ubuntu LTS EC2 instance with Docker Compose | ✅ | Implemented via `ec2_compose_host` module. |
| AMI resolved through Terraform data source | ✅ | No committed fixed AMI default found. |
| External sensitive hostname inputs | ✅ | Variables and workflow use external secrets/vars. |
| One central Cloudflare tunnel with Compose DNS origins | ✅ | `central_connector_mode = true`; Compose service DNS routes. |
| SSM deploy flow instead of ECS service updates | ✅ | Workflow invokes `/opt/arte-chatbot/deploy.sh sha-${{ github.sha }}` through SSM. |
| Secrets stay in Secrets Manager/SSM | ✅ | Runtime secret ARNs and SSM secret module used; raw tunnel token not exposed in outputs. |

## Issues Found

### CRITICAL

None.

### WARNING

- Live production verification was not executed because AWS/Cloudflare credentials, production secrets, SSM Run Command access, real DNS, and production host access are unavailable in this workspace.
- `terraform plan` was not run; local validation proves syntax/module coherence, not real provider-side changes.
- Runtime-only scenarios remain partial until operators verify SSM deploy, `docker compose ps`, Cloudflare public URL health, S3/secret access, browser CORS behavior, and rollback against the production environment.
- Coverage metrics were unavailable because `pytest-cov` is not installed.

### SUGGESTION

- Add a future live cutover checklist artifact with exact commands and expected outputs for AMI selection, SSM deploy status, Compose services, public URL health, and rollback rehearsal once credentials are available.

## Final Verdict

**PASS WITH WARNINGS**

The change is locally verified and coherent with proposal, design, tasks, and specs. The remaining warnings are expected environment limitations for live production proof, not local implementation blockers.
