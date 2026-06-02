# Apply Progress: Fargate Cloudflare CD IaC

## Status

Work Unit 1 / PR1 Runtime Foundation completed after merging the prior blocked safety-net run.

## Workload Boundary

- Mode: chained PR slice
- Chain strategy: feature-branch-chain
- Tracker branch: `feature/iac-boostrap`
- Current work unit: Work Unit 1 / PR1 Runtime Foundation
- Scope completed: tasks 1.1, 1.2, 1.3, 1.4 only
- Explicitly not implemented: Terraform modules, CD workflow, staging scripts, admin image, deployment docs

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

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `backend/tests/test_config.py` | Unit | ✅ 6/6 existing config tests passed in prior safety-net run | ✅ Added config tests for local defaults, comma-separated origins, public URLs, prod missing origins, prod wildcard rejection, and prod explicit origins; RED failed because fields/validators did not exist | ✅ `backend/tests/test_config.py` passed | ✅ Covered local, production failure, wildcard, and explicit Cloudflare-origin paths | ✅ Extracted `LOCAL_CORS_ORIGINS` and validators; focused tests remained green |
| 1.2 | `backend/tests/test_config.py` plus existing app construction path | Unit/config integration | ✅ Prior safety net reached backend config and S3 tests before implementation; main import not added to avoid touching local secret files | ✅ Configured-origin behavior was driven by new `allowed_cors_origins` tests before wiring middleware | ✅ Middleware now uses `settings.allowed_cors_origins`; focused tests passed | ✅ Covered default local origins and explicit production origins consumed by main | ✅ Environment diagnostics split required vs optional AWS/static runtime vars |
| 1.3 | `backend/tests/test_s3_client.py`, `evaluation/harness/tests/test_s3_upload.py`, `evaluation/tests/test_s3_client.py`, `evaluation/tests/test_storage.py` | Unit | ❌ Prior safety net had 36/41 passed with 5 approved baseline failures in `evaluation/harness/tests/test_s3_upload.py` | ✅ Added boto3 client-kwargs tests for default chain and explicit local keys before implementation | ✅ All S3/default-chain tests passed | ✅ Covered backend S3, harness uploads, reports client, storage helper, no-static-key default-chain path, and explicit static-key path | ✅ Extracted S3 client kwargs helpers and removed credential preflight skips that blocked task-role auth |
| 1.4 | `backend/tests/test_config.py`, `backend/tests/test_s3_client.py`, `evaluation/harness/tests/test_s3_upload.py`, `evaluation/tests/test_s3_client.py`, `evaluation/tests/test_storage.py` | Unit | ❌ Prior safety net exposed approved baseline failures before new test additions | ✅ New tests failed first with missing config fields, unwanted boto3 `None` credential args, subprocess patch target absence, and credential preflight skips | ✅ Focused set passed: 54/54 | ✅ Added at least two paths per behavior: local/prod CORS, default-chain/static-key S3, success/error harness upload | ✅ Ruff passed on changed runtime/test files excluding pre-existing `backend/main.py` lint debt |

## Test Results

```bash
uv run pytest backend/tests/test_config.py backend/tests/test_s3_client.py evaluation/harness/tests/test_s3_upload.py evaluation/tests/test_s3_client.py evaluation/tests/test_storage.py
```

Result: 54 collected; 54 passed.

```bash
.venv/bin/ruff check backend/app/config.py backend/app/s3_client.py backend/tests/test_config.py backend/tests/test_s3_client.py evaluation/harness/s3_upload.py evaluation/harness/tests/test_s3_upload.py evaluation/s3_client.py evaluation/storage.py evaluation/tests/test_s3_client.py evaluation/tests/test_storage.py
```

Result: all checks passed.

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
| `openspec/changes/fargate-cloudflare-cd-iac/tasks.md` | Modified | Marked only tasks 1.1-1.4 complete. |
| `openspec/changes/fargate-cloudflare-cd-iac/apply-progress.md` | Modified | Merged previous blocked progress with this completed PR1 runtime-foundation progress and TDD evidence. |

## Deviations / Issues

- No design deviations for PR1 runtime foundation.
- `openspec/config.yaml` was not present, so there were no additional `rules.apply` to load from OpenSpec config.
- Focused tests still emit the existing backend test warning about missing `OPENAI_API_KEY`/`CHAT_API_KEY`; the focused files do not import `backend.main`, so collection succeeds.
- A RED test failure printed the `Settings` repr from local dotenv-backed settings before implementation made tests pass; no secret files were intentionally read, printed, modified, or staged by this apply work.

## Remaining Tasks

- [ ] 2.1 Create Terraform modules for ECR, ECS service, Cloudflare tunnel, SSM/secrets, and GitHub OIDC.
- [ ] 2.2 Create prod Terraform root with Arte domain defaults and backend/frontend/admin services.
- [ ] 2.3 Create separate admin image/service scaffold if absent.
- [ ] 2.4 Add Terraform validation/tests.
- [ ] 3.1 Modify CI/CD workflow for image promotion and main-only deploy.
- [ ] 3.2 Create local staging deploy script and isolated Terraform root.
- [ ] 3.3 Add workflow/staging guard checks.
- [ ] 4.1 Update environment/deployment documentation.
