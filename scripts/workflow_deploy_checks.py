"""Static checks for Lambda-only production delivery workflows.

The checks read repository files only. They intentionally avoid GitHub, AWS,
Cloudflare, Docker, and Terraform calls so they can run safely in PR CI.
"""

from pathlib import Path
import re


WORKFLOW_PATH = Path(".github/workflows/ci.yml")
PREVIEW_CLEANUP_WORKFLOW_PATH = Path(".github/workflows/lambda-preview-cleanup.yml")
PYTHON_VERSION_PATH = Path(".python-version")
LAMBDA_BACKEND_VARIABLES_PATH = Path(
    "infra/terraform/modules/lambda_backend/variables.tf"
)
SERVICES = ("backend", "frontend", "admin")


def check_workflow_deploy(project_root: Path) -> list[str]:
    """Return static findings for the production deploy workflow contract."""
    workflow = _read(project_root / WORKFLOW_PATH)
    preview_cleanup_workflow = _read(project_root / PREVIEW_CLEANUP_WORKFLOW_PATH)
    local_python_version = _read(project_root / PYTHON_VERSION_PATH).strip()
    lambda_variables = _read(project_root / LAMBDA_BACKEND_VARIABLES_PATH)
    publish_release_job = _job_block(workflow, "publish-release-images")
    publish_candidate_job = _job_block(workflow, "publish-candidate-images")
    cutover_job = _job_block(workflow, "cutover-prerequisites")
    promote_job = _job_block(workflow, "promote-lambda-production")
    verify_job = _job_block(workflow, "verify-lambda-production")
    preview_deploy_job = _job_block(workflow, "deploy-lambda-preview")
    preview_smoke_job = _job_block(workflow, "smoke-lambda-preview")
    preview_comment_job = _job_block(workflow, "comment-lambda-preview")

    findings: list[str] = []
    findings.extend(
        _check_main_deploy_gates(
            workflow,
            promote_job,
            verify_job,
            publish_release_job,
            publish_candidate_job,
        )
    )
    findings.extend(_check_lambda_production_inputs(promote_job, verify_job))
    findings.extend(_check_no_ec2_compose_delivery(workflow))
    findings.extend(_check_lambda_delivery(workflow, cutover_job, promote_job))
    findings.extend(_check_fixed_staging_optional(workflow, cutover_job))
    findings.extend(
        _check_lambda_preview_delivery(
            preview_deploy_job,
            preview_smoke_job,
            preview_comment_job,
            preview_cleanup_workflow,
        )
    )
    findings.extend(
        _check_lambda_python_runtime_alignment(
            workflow,
            lambda_variables,
            local_python_version,
        )
    )
    return findings


def _check_fixed_staging_optional(workflow: str, cutover_job: str) -> list[str]:
    findings: list[str] = []
    staging_deploy_job = _job_block(workflow, "deploy-lambda-staging")
    staging_smoke_job = _job_block(workflow, "smoke-lambda-staging")

    if not staging_deploy_job or not _contains_all(
        staging_deploy_job,
        [
            "vars.LAMBDA_STAGING_ENABLED == 'true'",
            "workflow_dispatch",
            "inputs.action == 'deploy-lambda'",
        ],
    ):
        findings.append(
            "fixed Lambda staging deploy must be optional for main production cutover"
        )

    staging_smoke_guard = "if: needs.deploy-lambda-staging.result == 'success'"
    if not staging_smoke_job or staging_smoke_guard not in staging_smoke_job:
        findings.append(
            "fixed Lambda staging smoke must run only after staging deploys"
        )

    if not cutover_job or not _contains_all(
        cutover_job,
        [
            "always()",
            "needs: [lambda-package, evaluation, deploy-lambda-staging, smoke-lambda-staging]",
            "LAMBDA_STAGING_ENABLED",
            "needs.smoke-lambda-staging.result",
            "Fixed Lambda staging is disabled; production cutover prerequisites continue.",
        ],
    ):
        findings.append(
            "production cutover must continue when fixed Lambda staging is disabled"
        )

    return findings


def _check_lambda_preview_delivery(
    preview_deploy_job: str,
    preview_smoke_job: str,
    preview_comment_job: str,
    preview_cleanup_workflow: str,
) -> list[str]:
    findings: list[str] = []

    if not preview_deploy_job or not _contains_all(
        preview_deploy_job,
        [
            "needs: [lambda-package, evaluation]",
            "github.event_name == 'pull_request'",
            "github.event.pull_request.head.repo.full_name == github.repository",
            "vars.LAMBDA_PREVIEW_ENABLED == 'true'",
            "actions/download-artifact@v4",
            "needs.lambda-package.outputs.package-sha256",
            "hashicorp/setup-terraform@v3",
            "terraform -chdir=infra/terraform/envs/pr-preview init",
            (
                "terraform -chdir=infra/terraform/envs/pr-preview "
                "apply -auto-approve -input=false"
            ),
            '-backend-config="key=${STATE_KEY}"',
            "TF_VAR_pr_number",
            "TF_VAR_backend_runtime_secret_arns",
        ],
    ):
        findings.append(
            "lambda PR preview deploy must use the scanned package artifact and isolated Terraform state"
        )

    if not preview_smoke_job or not _contains_all(
        preview_smoke_job,
        [
            "scripts/lambda_smoke.py",
            '--base-url "${PREVIEW_API_URL}"',
            "Resolve preview chat API key from runtime secret ARN",
            "aws secretsmanager get-secret-value",
            "aws ssm get-parameter",
            "::add-mask::${PREVIEW_CHAT_API_KEY}",
            "--require-source-docs",
            '--state-table-name "${PREVIEW_STATE_TABLE}"',
            '--state-key-prefix "${PREVIEW_STATE_PREFIX}"',
            '--chat-api-key "${PREVIEW_CHAT_API_KEY}"',
            (
                "evaluation.harness.run --sprint lambda-preview-pr-"
                "${{ github.event.pull_request.number }} --no-upload"
            ),
            'CHAT_API_KEY="${PREVIEW_CHAT_API_KEY}"',
            (
                "lambda-preview-evaluation-results-pr-"
                "${{ github.event.pull_request.number }}"
            ),
        ],
    ):
        findings.append(
            "lambda PR preview smoke must validate the direct endpoint, state isolation, and evaluation harness"
        )

    if not preview_comment_job or not _contains_all(
        preview_comment_job,
        [
            "pull-requests: write",
            "gh pr comment",
            "--edit-last",
            "--create-if-none",
            (
                "This preview is isolated per PR and is destroyed automatically when "
                "the PR closes."
            ),
        ],
    ):
        findings.append("lambda PR preview must comment URL and validation result")

    if not preview_cleanup_workflow or not _contains_all(
        preview_cleanup_workflow,
        [
            "types: [closed]",
            "github.event.pull_request.head.repo.full_name == github.repository",
            "vars.LAMBDA_PREVIEW_ENABLED == 'true'",
            (
                "terraform -chdir=infra/terraform/envs/pr-preview "
                "destroy -auto-approve -input=false"
            ),
            "TF_PREVIEW_STATE_PREFIX",
            "gh pr comment",
        ],
    ):
        findings.append(
            "lambda PR preview cleanup must destroy Terraform state on PR close"
        )

    return findings


def _check_main_deploy_gates(
    workflow: str,
    promote_job: str,
    verify_job: str,
    publish_release_job: str,
    publish_candidate_job: str,
) -> list[str]:
    findings: list[str] = []

    main_guard = "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    if not promote_job or main_guard not in promote_job:
        findings.append(
            "production Lambda promotion job must run only on push events to refs/heads/main"
        )
    if not verify_job or main_guard not in verify_job:
        findings.append(
            "production Lambda smoke job must run only on push events to refs/heads/main"
        )

    if (
        not promote_job
        or "needs: [lambda-package, cutover-prerequisites]" not in promote_job
    ):
        findings.append(
            "production Lambda promotion must depend on package and cutover gates"
        )
    if not publish_release_job or "needs: evaluation" not in publish_release_job:
        findings.append("release image promotion must still wait for evaluation gates")

    pr_candidate_guard = "github.event_name == 'pull_request'" in publish_candidate_job
    production_jobs = "\n".join([promote_job, verify_job])
    deploy_mentions_pr = "pull_request" in production_jobs if production_jobs else True
    if not pr_candidate_guard or deploy_mentions_pr:
        findings.append("pull requests must not have any production deploy path")

    if "deploy-production:" in workflow:
        findings.append("legacy EC2 deploy-production job must be removed")

    return findings


def _check_lambda_production_inputs(promote_job: str, verify_job: str) -> list[str]:
    findings: list[str] = []

    required_promote_env = [
        "LAMBDA_PROD_FUNCTION_NAME: ${{ vars.LAMBDA_PROD_FUNCTION_NAME }}",
        "LAMBDA_PROD_ALIAS_NAME: ${{ vars.LAMBDA_PROD_ALIAS_NAME || 'live' }}",
        "LAMBDA_PROD_API_URL: ${{ vars.LAMBDA_PROD_API_URL }}",
        "LAMBDA_PROD_STATE_TABLE_NAME: ${{ vars.LAMBDA_PROD_STATE_TABLE_NAME }}",
        "LAMBDA_PROD_STATE_KEY_PREFIX: ${{ vars.LAMBDA_PROD_STATE_KEY_PREFIX || 'prod' }}",
    ]
    if not promote_job or not _contains_all(promote_job, required_promote_env):
        findings.append(
            "production Lambda promotion must use Lambda function, alias, API, and state variables"
        )

    if (
        not promote_job
        or "AWS_DEPLOY_ROLE_ARN: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}" not in promote_job
    ):
        findings.append("production Lambda promotion must use AWS deploy role secret")

    if not verify_job or not _contains_all(
        verify_job,
        [
            "scripts/lambda_smoke.py",
            '--base-url "${{ needs.promote-lambda-production.outputs.api-url }}"',
            "--environment production",
            '--state-table-name "${{ needs.promote-lambda-production.outputs.state-table-name }}"',
            '--state-key-prefix "${{ needs.promote-lambda-production.outputs.state-key-prefix }}"',
        ],
    ):
        findings.append(
            "production Lambda verification must smoke the API Gateway endpoint and DynamoDB state"
        )

    return findings


def _check_no_ec2_compose_delivery(workflow: str) -> list[str]:
    forbidden_tokens = [
        "TF_VAR_vpc_id",
        "TF_VAR_public_subnet_id",
        "TF_VAR_edge_tunnel_secret",
        "TF_VAR_cloudflare_account_id",
        "TF_VAR_cloudflare_zone_id",
        "ec2_compose_host",
        "aws ssm send-command",
        "AWS-RunShellScript",
        "/opt/arte-chatbot/deploy.sh",
        "Verify backend health through Cloudflare",
        "LAMBDA_CUTOVER_REVERT_CONFIRMED",
        "existing EC2 Compose deployment path",
    ]
    if any(token in workflow for token in forbidden_tokens):
        return [
            "workflow must not keep EC2 Compose, Cloudflare Tunnel, VPC/subnet, or revert-confirmation deploy paths"
        ]
    return []


def _check_lambda_delivery(
    workflow: str, cutover_job: str, promote_job: str
) -> list[str]:
    findings: list[str] = []
    lambda_package_job = _job_block(workflow, "lambda-package")
    staging_deploy_job = _job_block(workflow, "deploy-lambda-staging")
    staging_smoke_job = _job_block(workflow, "smoke-lambda-staging")
    rollback_job = _job_block(workflow, "rollback-lambda-production")

    if not lambda_package_job or not _contains_all(
        lambda_package_job,
        [
            "scripts/build_lambda_package.py --output",
            "--scan-only",
            "backend/tests/test_lambda_runtime.py",
            "scripts/tests/test_lambda_delivery_scripts.py",
            "actions/upload-artifact@v4",
            "package-sha256",
        ],
    ):
        findings.append(
            "lambda package job must test, build, scan, and upload one zip artifact"
        )

    if not staging_deploy_job or not _contains_all(
        staging_deploy_job,
        [
            "needs: [lambda-package, evaluation]",
            "aws-actions/configure-aws-credentials@v4",
            "LAMBDA_STAGING_FUNCTION_NAME",
            "LAMBDA_STAGING_ALIAS_NAME",
            "LAMBDA_STAGING_API_URL",
            "aws lambda update-function-code",
            "aws lambda update-alias",
            "needs.lambda-package.outputs.package-sha256",
        ],
    ):
        findings.append(
            "lambda staging deploy must use OIDC and the scanned package artifact"
        )

    if not staging_smoke_job or not _contains_all(
        staging_smoke_job,
        [
            "scripts/lambda_smoke.py",
            "--environment staging",
            "--require-source-docs",
            "LAMBDA_STAGING_IAM_DENIED_DYNAMODB_TABLE_NAME",
            "PROD_BACKEND_HOSTNAME",
            "evaluation.harness.run --sprint lambda-staging --no-upload",
        ],
    ):
        findings.append(
            "lambda staging smoke must validate chat, File Inputs, DynamoDB, IAM denial, and URL isolation"
        )

    if not cutover_job or not _contains_all(
        cutover_job,
        [
            "Lambda-only production Terraform cutover confirmed",
            'module "compose_host"',
            'module "edge_tunnel"',
            'variable "vpc_id"',
            'variable "public_subnet_id"',
            'variable "edge_tunnel_secret"',
        ],
    ):
        findings.append(
            "lambda cutover must verify production Terraform is Lambda-only"
        )

    if not promote_job or not _contains_all(
        promote_job,
        [
            "needs: [lambda-package, cutover-prerequisites]",
            "Download exact Lambda package artifact",
            "needs.lambda-package.outputs.package-sha256",
            "aws lambda get-alias",
            "previous-version",
            "aws lambda update-function-code",
            "aws lambda update-alias",
            "LAMBDA_PROD_FUNCTION_NAME",
        ],
    ):
        findings.append(
            "lambda production promotion must use the same package and capture rollback target"
        )

    if not rollback_job or not _contains_all(
        rollback_job,
        [
            "scripts/lambda_rollback.py rollback-alias",
            "LAMBDA_ROLLBACK_TARGET_VERSION",
            "needs.promote-lambda-production.outputs.previous-version",
        ],
    ):
        findings.append(
            "lambda rollback job must restore a discovered previous alias version"
        )

    return findings


def _check_lambda_python_runtime_alignment(
    workflow: str,
    lambda_variables: str,
    local_python_version: str,
) -> list[str]:
    workflow_python = _workflow_python_version(workflow)
    terraform_python = _terraform_lambda_python_version(lambda_variables)
    if (
        not workflow_python
        or not terraform_python
        or workflow_python != terraform_python
        or (local_python_version and local_python_version != terraform_python)
    ):
        return ["lambda package Python version must match Terraform Lambda runtime"]
    return []


def _job_block(workflow: str, job_name: str) -> str:
    pattern = re.compile(
        rf"^  {re.escape(job_name)}:\n(?P<body>(?:    .+\n|\n)+)", re.MULTILINE
    )
    match = pattern.search(workflow)
    return match.group(0) if match else ""


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)


def _workflow_python_version(workflow: str) -> str:
    match = re.search(r'PYTHON_VERSION:\s*["\']?(?P<version>\d+\.\d+)["\']?', workflow)
    return match.group("version") if match else ""


def _terraform_lambda_python_version(lambda_variables: str) -> str:
    runtime_block = _variable_block(lambda_variables, "runtime")
    match = re.search(
        r'default\s*=\s*["\']python(?P<version>\d+\.\d+)["\']', runtime_block
    )
    return match.group("version") if match else ""


def _variable_block(text: str, variable_name: str) -> str:
    pattern = re.compile(
        rf'variable\s+"{re.escape(variable_name)}"\s+{{(?P<body>.*?)\n}}',
        re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(0) if match else ""
