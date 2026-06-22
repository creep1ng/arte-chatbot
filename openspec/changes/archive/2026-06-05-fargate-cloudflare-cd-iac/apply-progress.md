# Apply Progress: Fargate Cloudflare CD IaC

## Status

Work Units 1-3 are complete. Runtime config, Terraform foundation, CD workflow,
local staging, guard checks, and deployment docs are implemented; no deploy/apply
has been executed yet.

## Workload Boundary

- Mode: chained PR slice
- Chain strategy: feature-branch-chain
- Tracker branch: `feature/iac-boostrap`
- Current work unit: Work Unit 3 / PR3 CD + local staging + docs
- Scope completed: tasks 1.1-1.4, 2.1-2.4, 3.1-3.3, and 4.1
- Explicitly not executed: Terraform apply, ECS deploy, Cloudflare DNS/tunnel creation

## Prior Safety-Net History

The previous apply attempt stopped before implementation because Strict TDD safety-net tests failed in `evaluation/harness/tests/test_s3_upload.py`.
The user-approved continuation scoped those baseline fixes into PR1 because they are directly related to runtime S3/default credential-chain behavior.

Prior command:

```bash
uv run pytest backend/tests/test_config.py backend/tests/test_s3_client.py evaluation/harness/tests/test_s3_upload.py
```

Prior result: 41 collected; 36 passed; 5 failed.

Prior blocking failures:

- `evaluation/harness/tests/test_s3_upload.py::TestGenerateMetadata::test_returns_expected_fields`
- `evaluation/harness/tests/test_s3_upload.py::TestGenerateMetadata::test_fallback_on_git_failure`
- `evaluation/harness/tests/test_s3_upload.py::TestUploadResults::test_handles_s3_error_gracefully`
- `evaluation/harness/tests/test_s3_upload.py::TestUploadResultsWithMetadata::test_returns_none_when_credentials_missing`
- `evaluation/harness/tests/test_s3_upload.py::TestUploadResultsWithMetadata::test_uploads_results_plus_metadata`

## Completed Tasks

- [x] 1.1 Added backend runtime settings for `APP_ENV`, public URLs, and comma-separated `ALLOWED_CORS_ORIGINS`; production rejects missing/default origins and wildcard origins.
- [x] 1.2 Wired FastAPI CORS middleware to `settings.allowed_cors_origins` and changed environment diagnostics so static AWS keys are optional runtime inputs, not required deployed env.
- [x] 1.3 Updated backend and evaluation S3 clients/uploads to pass only `region_name` when explicit local keys are absent, preserving boto3's default credential provider chain for ECS task roles/OIDC.
- [x] 1.4 Added/extended tests for production CORS fail-fast, local origins, public URL config, boto3 client kwargs, evaluation storage/report clients, and the approved `s3_upload` baseline fixes.
- [x] 2.1 Added Terraform modules for ECR, ECS Fargate services, Cloudflare tunnels, SSM/Secrets Manager values, and GitHub OIDC with least-privilege IAM, logs, outbound security groups, sidecar support, and sensitive tunnel-token handling.
- [x] 2.2 Added the production Terraform root with `domain_name` defaulting to `artesolutions.com.co`, derived `api`, `app`, and `admin` hostnames, separate ECR repos/services/task definitions, Cloudflare sidecars, and backend `ALLOWED_CORS_ORIGINS` runtime config.
- [x] 2.3 Added a separate `admin` nginx image scaffold and minimal static source, independent from the frontend route/image.
- [x] 2.4 Added static Terraform foundation validation checks covering scoped tunnels, no mixed unreachable localhost origins, sensitive token/secret outputs, prod/staging name isolation, and admin image separation.
- [x] 3.1 Updated GitHub Actions to build backend, frontend, and admin images; publish PR candidate tags after health/evaluation gates; publish SHA release tags; and deploy production only from `main` using OIDC and Terraform variables.
- [x] 3.2 Added local-staging Terraform root and `scripts/deploy-local-staging.sh` requiring explicit ECR tags, unique staging hostnames, non-CI execution, isolated state/params/secrets, Cloudflare token input, and expiration no later than 3 days.
- [x] 3.3 Added static guard checks for PR no-prod-deploy, CI staging rejection, production URL/name rejection, rollback-visible SHA tags, required Terraform inputs, and local staging safety.
- [x] 4.1 Updated `.env.example`, `README.md`, and `docs/deployment.md` with domain, IAM/default credential-chain usage, ECR tags, prod deploy flow, local staging cleanup, and handoff/access requirements.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `backend/tests/test_config.py` | Unit | ✅ 6/6 existing config tests passed in prior safety-net run | ✅ Added config tests for local defaults, comma-separated origins, public URLs, prod missing origins, prod wildcard rejection, and prod explicit origins; RED failed because fields/validators did not exist | ✅ `backend/tests/test_config.py` passed | ✅ Covered local, production failure, wildcard, and explicit Cloudflare-origin paths | ✅ Extracted `LOCAL_CORS_ORIGINS` and validators; focused tests remained green |
| 1.2 | `backend/tests/test_config.py` plus existing app construction path | Unit/config integration | ✅ Prior safety net reached backend config and S3 tests before implementation; main import not added to avoid touching local secret files | ✅ Configured-origin behavior was driven by new `allowed_cors_origins` tests before wiring middleware | ✅ Middleware now uses `settings.allowed_cors_origins`; focused tests passed | ✅ Covered default local origins and explicit production origins consumed by main | ✅ Environment diagnostics split required vs optional AWS/static runtime vars |
| 1.3 | `backend/tests/test_s3_client.py`, `evaluation/harness/tests/test_s3_upload.py`, `evaluation/tests/test_s3_client.py`, `evaluation/tests/test_storage.py` | Unit | ❌ Prior safety net had 36/41 passed with 5 approved baseline failures in `evaluation/harness/tests/test_s3_upload.py` | ✅ Added boto3 client-kwargs tests for default chain and explicit local keys before implementation | ✅ All S3/default-chain tests passed | ✅ Covered backend S3, harness uploads, reports client, storage helper, no-static-key default-chain path, and explicit static-key path | ✅ Extracted S3 client kwargs helpers and removed credential preflight skips that blocked task-role auth |
| 1.4 | `backend/tests/test_config.py`, `backend/tests/test_s3_client.py`, `evaluation/harness/tests/test_s3_upload.py`, `evaluation/tests/test_s3_client.py`, `evaluation/tests/test_storage.py` | Unit | ❌ Prior safety net exposed approved baseline failures before new test additions | ✅ New tests failed first with missing config fields, unwanted boto3 `None` credential args, subprocess patch target absence, and credential preflight skips | ✅ Focused set passed: 54/54 | ✅ Added at least two paths per behavior: local/prod CORS, default-chain/static-key S3, success/error harness upload | ✅ Ruff passed on changed runtime/test files excluding pre-existing `backend/main.py` lint debt |
| 2.1 | `scripts/tests/test_terraform_foundation.py`, `scripts/terraform_foundation_checks.py` | Static IaC validation | N/A (new files) | ✅ Tests failed with missing Terraform module/root findings before implementation | ✅ Terraform modules satisfied scoped tunnel, sensitive output, and IAM/logging/security-group checks | ✅ Covered Cloudflare tunnel scoping plus token/secret sensitivity paths | ✅ `terraform fmt -recursive` and ruff passed |
| 2.2 | `scripts/tests/test_terraform_foundation.py`, `scripts/terraform_foundation_checks.py` | Static IaC validation | N/A (new files) | ✅ Tests failed with missing prod root/domain/hostname findings before implementation | ✅ Prod root passed derived hostnames/domain/default CORS/origin checks | ✅ Covered backend `localhost:8000`, frontend/admin `localhost:3000`, and prod name isolation | ✅ Terraform files formatted recursively |
| 2.3 | `scripts/tests/test_terraform_foundation.py`, `scripts/terraform_foundation_checks.py` | Static scaffold validation | N/A (new files) | ✅ Test failed because admin Dockerfile/nginx/source did not exist | ✅ Admin image scaffold passed separate-image checks | ✅ Covered Dockerfile source path and nginx port 3000 | ✅ Minimal static source kept separate from frontend |
| 2.4 | `scripts/tests/test_terraform_foundation.py`, `scripts/terraform_foundation_checks.py` | Unit/static validation | N/A (new files) | ✅ Check script/tests were written before Terraform implementation and failed on missing controls | ✅ 5/5 PR2 validation tests passed | ✅ Validated scoped tunnels, no shared unreachable localhost origins, sensitive outputs, prod/staging isolation, and admin separation | ✅ Check script refactored after `terraform fmt` to avoid brittle spacing assertions; tests remained green |
| 3.1 | `scripts/tests/test_cd_and_staging_guards.py`, `scripts/deployment_guard_checks.py` | Static workflow validation | N/A (workflow guard added) | ✅ Tests/checks required all images, gated candidate publish, main-only deploy, OIDC, and Terraform inputs before accepting workflow | ✅ 8/8 CD/staging guard tests passed | ✅ Covered PR and main paths plus rollback-visible tags | ✅ Workflow kept staging out of CI and moved required deploy inputs into explicit env |
| 3.2 | `scripts/tests/test_cd_and_staging_guards.py` | Script/Terraform validation | N/A (new script/root) | ✅ Tests failed until script rejected CI, implicit tags, prod names, long expiration, and missing deploy inputs | ✅ Local staging root validated with Terraform provider schemas | ✅ Covered unique hostnames, local backend state, isolated params/secrets, and required TF_VAR inputs | ✅ Script fail-fast ordering preserves useful error messages before Terraform runs |
| 3.3 | `scripts/tests/test_cd_and_staging_guards.py`, `scripts/deployment_guard_checks.py` | Static guard validation | N/A (new checks) | ✅ Guard tests encoded no-prod-deploy, CI staging rejection, production URL/name rejection, rollback SHA tags, and required inputs | ✅ Guard tests and ruff passed | ✅ Checked workflow, script, and Terraform root without cloud/API calls | ✅ Static checks remained safe for CI |
| 4.1 | `README.md`, `.env.example`, `docs/deployment.md` | Docs/config validation | N/A (docs update) | ✅ Documentation checklist was derived from deployment requirements before handoff | ✅ Docs now list required AWS, Cloudflare, GitHub, env, and Terraform inputs | ✅ Covered prod deploy, local staging, cleanup, verification, and secrets rules | ✅ Kept secrets out of committed examples |

## Test Results

```bash
uv run pytest backend/tests/test_config.py backend/tests/test_s3_client.py evaluation/harness/tests/test_s3_upload.py evaluation/tests/test_s3_client.py evaluation/tests/test_storage.py
```

Result: 54 collected; 54 passed.

```bash
.venv/bin/ruff check backend/app/config.py backend/app/s3_client.py backend/tests/test_config.py backend/tests/test_s3_client.py evaluation/harness/s3_upload.py evaluation/harness/tests/test_s3_upload.py evaluation/s3_client.py evaluation/storage.py evaluation/tests/test_s3_client.py evaluation/tests/test_storage.py
```

Result: all checks passed.

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest scripts/tests/test_terraform_foundation.py
```

Result: 5 collected; 5 passed.

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check scripts/terraform_foundation_checks.py scripts/tests/test_terraform_foundation.py
```

Result: all checks passed.

```bash
terraform fmt -recursive infra/terraform
terraform fmt -check -recursive infra/terraform
```

Result: formatting applied, then check passed.

```bash
terraform validate
```

Initial result: failed during validation because the Cloudflare module needed an explicit
`cloudflare/cloudflare` provider source and the v5 provider exposes the connector
token through `data.cloudflare_zero_trust_tunnel_cloudflared_token`, not a direct
resource attribute.

```bash
terraform -chdir=infra/terraform/envs/prod init -backend=false -upgrade
terraform -chdir=infra/terraform/envs/prod validate
```

Final result: initialized providers successfully and `terraform validate` passed.

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest scripts/tests/test_cd_and_staging_guards.py
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check scripts/deployment_guard_checks.py scripts/tests/test_cd_and_staging_guards.py
terraform fmt -check -recursive infra/terraform/envs/local-staging
terraform -chdir=infra/terraform/envs/local-staging validate
```

Result: 8 guard tests passed, ruff passed, local-staging Terraform formatting check passed,
and local-staging `terraform validate` passed after provider initialization.

Note: `backend/main.py` was excluded from the focused ruff command because it has pre-existing lint debt unrelated to this work unit (`E402`, duplicate route definition, unused local variable). The changed main behavior is limited to CORS configuration and environment diagnostics.

## Files Changed

| File | Action | What changed |
|------|--------|--------------|
| `backend/app/config.py` | Modified | Added runtime public URL/CORS settings, comma-separated origin parsing, local defaults, and production fail-fast validation. |
| `backend/main.py` | Modified | CORS middleware now uses configured origins; AWS static keys are logged as optional rather than required env vars. |
| `backend/app/s3_client.py` | Modified | Added boto3 kwargs helper that omits static credential args when absent so default credential chain can resolve ECS task role credentials. |
| `evaluation/s3_client.py` | Modified | Removed hard failure on missing static keys; uses default credential chain unless explicit local keys are present. |
| `evaluation/storage.py` | Modified | Removed missing-static-key upload skip; boto3 client now uses default credential chain when keys are absent. |
| `evaluation/harness/s3_upload.py` | Modified | Fixed approved baseline failures and switched uploads/metadata uploads to default credential-chain behavior. |
| `backend/tests/test_config.py` | Modified | Added runtime CORS/public URL config tests. |
| `backend/tests/test_s3_client.py` | Modified | Added boto3 client argument tests for default-chain and explicit local-key paths. |
| `evaluation/harness/tests/test_s3_upload.py` | Modified | Updated baseline tests for module-level subprocess patching, ClientError handling, and default credential-chain upload behavior. |
| `evaluation/tests/test_s3_client.py` | Created | Added evaluation reports client credential-chain tests. |
| `evaluation/tests/test_storage.py` | Created | Added shared evaluation storage credential-chain tests. |
| `openspec/changes/fargate-cloudflare-cd-iac/tasks.md` | Modified | Marked tasks 2.1-2.4 complete while preserving PR1 task status. |
| `openspec/changes/fargate-cloudflare-cd-iac/apply-progress.md` | Modified | Merged previous blocked progress with completed PR1 and PR2 Terraform-foundation progress and TDD/static validation evidence. |
| `infra/terraform/modules/ecr/*` | Created | Reusable ECR repository module with scanning, encryption, lifecycle policy, and repository outputs. |
| `infra/terraform/modules/ecs_service/*` | Created | Reusable ECS Fargate service/task module with execution/task roles, least-privilege pull/log/secret policy, logs, outbound security group, health checks, and sidecar support. |
| `infra/terraform/modules/cloudflare_tunnel/*` | Created | Scoped Cloudflare tunnel/DNS module using `cloudflare_zero_trust_tunnel_cloudflared`, tunnel config, mixed-localhost-origin validation, and sensitive token output. |
| `infra/terraform/modules/ssm_secrets/*` | Created | Secrets Manager/SSM parameter module with sensitive outputs for runtime secret references. |
| `infra/terraform/modules/github_oidc/*` | Created | Optional least-privilege GitHub Actions OIDC deploy role module. |
| `infra/terraform/envs/prod/*` | Created | Production root with Arte domain defaults, separate backend/frontend/admin repos and ECS services, Cloudflare hostnames/tunnels, cloudflared sidecars, and backend runtime CORS/public URL config. |
| `admin/Dockerfile` | Created | Separate admin nginx image scaffold. |
| `admin/nginx.conf` | Created | Admin nginx config listening on port 3000. |
| `admin/src/index.html` | Created | Minimal admin placeholder source independent from frontend routing. |
| `scripts/terraform_foundation_checks.py` | Created | Safe static validation helper for Terraform foundation invariants. |
| `scripts/tests/test_terraform_foundation.py` | Created | Pytest coverage for scoped tunnels, sensitive outputs, prod isolation, and admin separation. |
| `.github/workflows/ci.yml` | Modified | Builds/publishes backend/frontend/admin images, gates ECR push after evaluation, and deploys prod only from main with OIDC and explicit Terraform inputs. |
| `infra/terraform/envs/local-staging/*` | Created | Local-only staging root with unique hostnames, isolated state, explicit ECR tags, staging secrets/params, and expiration metadata. |
| `scripts/deploy-local-staging.sh` | Created | Developer-run deploy helper that rejects CI, implicit tags, prod-like ids, long expirations, and missing deploy inputs before Terraform. |
| `scripts/deployment_guard_checks.py` | Created | Static guard checks for workflow and staging safety. |
| `scripts/tests/test_cd_and_staging_guards.py` | Created | Tests for CI/CD gating, staging isolation, explicit tags, and deploy input fail-fast behavior. |
| `.env.example` | Modified | Documents deployed runtime env, domain, immutable image tags, local staging values, and default credential-chain expectations. |
| `README.md` | Modified | Adds project structure, runtime config, CI/CD, local staging, testing, and security guidance. |
| `docs/deployment.md` | Created | Deployment guide and final handoff/access checklist for AWS, Cloudflare, GitHub, Terraform, and verification. |

## Deviations / Issues

- No design deviations for PR1 runtime foundation.
- No design deviations for PR2/PR3; Cloudflare tunnel token values are marked sensitive and stored into AWS Secrets Manager for ECS sidecars, but provider/state access still needs normal Terraform state protection.
- The `ssm_secrets` module uses non-sensitive key sets for `for_each` while keeping secret values sensitive; Terraform cannot safely use sensitive values directly as instance keys.
- `openspec/config.yaml` was not present, so there were no additional `rules.apply` to load from OpenSpec config.
- Focused tests still emit the existing backend test warning about missing `OPENAI_API_KEY`/`CHAT_API_KEY`; the focused files do not import `backend.main`, so collection succeeds.
- A RED test failure printed the `Settings` repr from local dotenv-backed settings before implementation made tests pass; no secret files were intentionally read, printed, modified, or staged by this apply work.

## Remaining Tasks

All apply tasks in `tasks.md` are complete. Next phases: verify, then deployment execution/rectification after required secrets/vars are confirmed.
