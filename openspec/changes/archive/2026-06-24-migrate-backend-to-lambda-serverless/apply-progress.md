# Apply Progress: Migrate Backend to Lambda Serverless

## Status

- Change: `migrate-backend-to-lambda-serverless`
- Delivery mode: feature-branch-chain cleanup slice
- Chain strategy: `feature-branch-chain`
- Current work unit: post-verification cleanup after failed verify findings
- Mode: Standard

## Completed Tasks

- [x] All implementation tasks recorded in `tasks.md` through production custom-domain cutover.
- [x] Post-verification cleanup fixed `.env.deploy` ignore coverage and updated `.env.example` for Lambda/API Gateway/DynamoDB/custom-domain semantics.
- [x] ADR/deployment wording now separates Cloudflare DNS custom-domain inputs from the retired Cloudflare Tunnel production runtime.
- [x] Superseded `low-cost-ec2-compose-exposure` artifacts were moved from active OpenSpec changes into the dated archive.
- [x] Active base specs were retired or updated so EC2/Fargate/Cloudflare Tunnel no longer appears as the current backend production path.
- [x] Legacy Phase 4 EC2 Compose checks were reworked into Lambda-only cleanup/coherence guards.

## Validation Results

| Command | Result | Notes |
|---|---|---|
| `openspec validate migrate-backend-to-lambda-serverless --strict` | ✅ Pass | Change is valid after cleanup. |
| `uv run pytest scripts/tests/test_workflow_deploy_checks.py scripts/tests/test_prod_terraform_wiring_checks.py scripts/tests/test_terraform_foundation.py scripts/tests/test_lambda_delivery_scripts.py scripts/tests/test_phase4_verification_checks.py scripts/tests/test_cd_and_staging_guards.py` | ✅ Pass | 32 workflow/deployment/Terraform/Lambda delivery guard tests passed. |
| `git check-ignore .env.deploy` | ✅ Pass | Returned `.env.deploy`. |
| `uv run ruff check scripts/phase4_verification_checks.py scripts/tests/test_phase4_verification_checks.py && uv run ruff format --check scripts/phase4_verification_checks.py scripts/tests/test_phase4_verification_checks.py` | ✅ Pass | Reworked cleanup guard scripts pass Ruff and formatting. |
| `git diff --check` | ✅ Pass | No whitespace errors in tracked diffs. |
| CI workflow validation signal | ⚠️ Fallback | `actionlint` is unavailable; repository workflow guard tests were run instead. |

## Deviations and Limitations

- Terraform modules for legacy EC2 Compose/Fargate/Cloudflare Tunnel were not deleted. They are preserved as historical/reusable code unless a later destructive cleanup explicitly removes them.
- No GitHub variables/secrets, AWS resources, or live Cloudflare settings were mutated during this cleanup.

## Workload / PR Boundary

- Mode: chained PR cleanup slice under the existing `feature-branch-chain`.
- Boundary: documentation/OpenSpec/static-guard cleanup only; no live deploy mutation and no Terraform module deletion.
