"""Static validation checks for the Terraform foundation scaffold.

These checks intentionally inspect repository files without requiring Terraform
provider initialization, so they are safe for PR validation and local TDD cycles.
"""

from pathlib import Path
import re


TERRAFORM_ROOT = Path("infra/terraform")
PROD_ROOT = TERRAFORM_ROOT / "envs" / "prod"
MODULE_ROOT = TERRAFORM_ROOT / "modules"
LOCAL_STAGING_ROOT = TERRAFORM_ROOT / "envs" / "local-staging"
PR_PREVIEW_ROOT = TERRAFORM_ROOT / "envs" / "pr-preview"


def check_foundation(project_root: Path) -> list[str]:
    """Return validation finding messages for the Terraform foundation scaffold."""
    findings: list[str] = []

    prod_main = _read(project_root / PROD_ROOT / "main.tf")
    prod_variables = _read(project_root / PROD_ROOT / "variables.tf")
    prod_outputs = _read(project_root / PROD_ROOT / "outputs.tf")
    tunnel_outputs = _read(
        project_root / MODULE_ROOT / "cloudflare_tunnel" / "outputs.tf"
    )
    secrets_outputs = _read(project_root / MODULE_ROOT / "ssm_secrets" / "outputs.tf")
    lambda_main = _read(project_root / MODULE_ROOT / "lambda_backend" / "main.tf")
    lambda_variables = _read(
        project_root / MODULE_ROOT / "lambda_backend" / "variables.tf"
    )
    lambda_outputs = _read(project_root / MODULE_ROOT / "lambda_backend" / "outputs.tf")
    local_staging_main = _read(project_root / LOCAL_STAGING_ROOT / "main.tf")
    local_staging_variables = _read(project_root / LOCAL_STAGING_ROOT / "variables.tf")
    local_staging_outputs = _read(project_root / LOCAL_STAGING_ROOT / "outputs.tf")
    pr_preview_main = _read(project_root / PR_PREVIEW_ROOT / "main.tf")
    pr_preview_variables = _read(project_root / PR_PREVIEW_ROOT / "variables.tf")
    pr_preview_outputs = _read(project_root / PR_PREVIEW_ROOT / "outputs.tf")
    pr_preview_providers = _read(project_root / PR_PREVIEW_ROOT / "providers.tf")
    github_oidc_main = _read(project_root / MODULE_ROOT / "github_oidc" / "main.tf")
    github_oidc_variables = _read(
        project_root / MODULE_ROOT / "github_oidc" / "variables.tf"
    )
    github_oidc_outputs = _read(
        project_root / MODULE_ROOT / "github_oidc" / "outputs.tf"
    )
    admin_dockerfile = _read(project_root / "admin" / "Dockerfile")
    admin_nginx = _read(project_root / "admin" / "nginx.conf")

    if any(
        token in prod_main + prod_variables + prod_outputs
        for token in [
            'module "edge_tunnel"',
            'module "compose_host"',
            'module "cloudflare_tunnel_secrets"',
            'variable "vpc_id"',
            'variable "public_subnet_id"',
            'variable "edge_tunnel_secret"',
            'output "ec2_compose_host"',
            'output "edge_tunnel"',
        ]
    ):
        findings.append(
            "prod must be Lambda-only without EC2 or Cloudflare Tunnel wiring"
        )

    if not _output_block_is_sensitive(tunnel_outputs, "tunnel_token"):
        findings.append("cloudflare tunnel token output must be sensitive")

    secret_outputs = ["secret_arns", "ssm_parameter_arns"]
    if any(
        not _output_block_is_sensitive(secrets_outputs, output)
        for output in secret_outputs
    ):
        findings.append("secret value outputs must be sensitive")

    if "tunnel_token" in prod_outputs.lower():
        findings.append("prod outputs must not expose tunnel tokens")

    hostname_variables = [
        _variable_block(prod_variables, "backend_hostname"),
        _variable_block(prod_variables, "frontend_hostname"),
        _variable_block(prod_variables, "admin_hostname"),
    ]
    if any(
        not block
        or "sensitive   = true" not in block
        or re.search(r"(?m)^\s*default\s*=", block)
        for block in hostname_variables
    ):
        findings.append(
            "prod hostname variables must be sensitive inputs without defaults"
        )

    if "hostname_labels" in prod_main or "var.domain_name" in prod_main:
        findings.append(
            "prod hostnames must not derive chatbot, app, and admin from domain_name"
        )

    if "staging" not in prod_variables or "strcontains" not in prod_variables:
        findings.append("prod name prefix must reject staging values")

    findings.extend(
        _check_lambda_backend_module(lambda_main, lambda_variables, lambda_outputs)
    )
    findings.extend(
        _check_local_staging_lambda(
            local_staging_main, local_staging_variables, local_staging_outputs
        )
    )
    findings.extend(
        _check_pr_preview_lambda(
            pr_preview_main,
            pr_preview_variables,
            pr_preview_outputs,
            pr_preview_providers,
        )
    )
    findings.extend(
        _check_github_oidc_role_separation(
            prod_main,
            prod_variables,
            prod_outputs,
            github_oidc_main,
            github_oidc_variables,
            github_oidc_outputs,
        )
    )

    if not admin_dockerfile:
        findings.append("admin Dockerfile must exist")
    if "listen 3000" not in admin_nginx:
        findings.append("admin nginx config must listen on port 3000")
    if "COPY admin/" not in admin_dockerfile or "COPY frontend/" in admin_dockerfile:
        findings.append("admin image must copy admin source, not frontend source")

    return findings


def _check_pr_preview_lambda(
    pr_preview_main: str,
    pr_preview_variables: str,
    pr_preview_outputs: str,
    pr_preview_providers: str,
) -> list[str]:
    findings: list[str] = []

    lambda_module = _module_block(pr_preview_main, "lambda_backend")
    if not lambda_module or not _contains_all(
        lambda_module,
        [
            'source = "../../modules/lambda_backend"',
            "local.preview_id",
            "state_key_prefix                           = local.preview_id",
            'alias_name           = "preview"',
            'SECRET_NAMESPACE    = "/arte-chatbot/pr-preview/${local.preview_id}/"',
            "CLEANUP_AFTER",
            "PULL_REQUEST_NUMBER",
        ],
    ):
        findings.append(
            "PR preview must wire an isolated lambda_backend module with preview alias and state prefix"
        )

    if not _contains_all(
        pr_preview_main,
        ["PreviewId", "PullRequest", "ExpiresAt", "CleanupAfter", "terraform_data"],
    ):
        findings.append("PR preview must tag resources for ownership and cleanup")

    if not _contains_all(
        pr_preview_variables,
        [
            'variable "pr_number"',
            'variable "pr_sha"',
            'variable "expiration_at"',
            'default     = "arte-chatbot-preview"',
            "Preview secret refs must be AWS ARNs, not plaintext secret values.",
            "default     = 259200",
        ],
    ):
        findings.append(
            "PR preview variables must require PR identity, cleanup deadline, and non-production secrets"
        )

    if not _contains_all(
        pr_preview_outputs,
        [
            'output "lambda_backend"',
            "preview_id",
            "invoke_url",
            "state_table_name",
            "state_key_prefix",
            "expiration_at",
        ],
    ):
        findings.append(
            "PR preview outputs must expose endpoint and isolated state metadata"
        )

    if 'backend "s3" {}' not in pr_preview_providers:
        findings.append("PR preview Terraform state must use S3 backend configuration")

    return findings


def _check_github_oidc_role_separation(
    prod_main: str,
    prod_variables: str,
    prod_outputs: str,
    oidc_main: str,
    oidc_variables: str,
    oidc_outputs: str,
) -> list[str]:
    """Require separate OIDC identities and an immutable preview runtime boundary."""
    findings: list[str] = []
    production_policy = _data_block(oidc_main, "aws_iam_policy_document", "deploy")
    preview_policy = _data_block(oidc_main, "aws_iam_policy_document", "preview_deploy")

    if (
        oidc_main.count('resource "aws_iam_openid_connect_provider" "github"') != 1
        or "repo:${var.github_owner}/${var.github_repository}:ref:refs/heads/${var.branch}"
        not in oidc_main
        or "repo:${var.github_owner}/${var.github_repository}:pull_request"
        not in oidc_main
        or 'resource "aws_iam_role" "this"' not in oidc_main
        or 'resource "aws_iam_role" "preview"' not in oidc_main
    ):
        findings.append(
            "GitHub OIDC must use one provider with separate main and pull_request role subjects"
        )

    if any(
        token in production_policy
        for token in [
            "apigateway:POST",
            "dynamodb:CreateTable",
            "iam:CreateRole",
            "lambda:CreateFunction",
        ]
    ):
        findings.append(
            "production deploy role must not create pull-request preview infrastructure"
        )

    if not _contains_all(
        oidc_main,
        [
            'resource "aws_iam_policy" "preview_lambda_boundary"',
            'resource "aws_iam_role" "preview_lambda"',
            "permissions_boundary = aws_iam_policy.preview_lambda_boundary.arn",
            'resource "aws_iam_role_policy_attachment" "preview_lambda_runtime"',
            "parameter/arte-chatbot/pr-preview/*",
            "secret:/arte-chatbot/pr-preview/*",
        ],
    ) or any(
        namespace
        in _data_block(oidc_main, "aws_iam_policy_document", "preview_lambda_boundary")
        for namespace in ["parameter/arte-chatbot/prod/", "secret:/arte-chatbot/prod/"]
    ):
        findings.append(
            "preview Lambda role must have a foundation-managed boundary limited to preview secrets"
        )

    if not _contains_all(
        preview_policy,
        [
            "aws_iam_role.preview_lambda.arn",
            'values   = ["lambda.amazonaws.com"]',
            "${var.preview_state_key_prefix}/*",
            "local.preview_lambda_arns",
            "local.preview_table_arns",
        ],
    ) or any(
        action in preview_policy
        for action in [
            "iam:CreateRole",
            "iam:DeleteRolePermissionsBoundary",
            "iam:PutRolePermissionsBoundary",
        ]
    ):
        findings.append(
            "preview deploy role must pass only the foundation runtime role and manage prefixed resources"
        )

    preview_role_variable = _variable_block(prod_variables, "github_preview_role_name")
    if not _contains_all(
        prod_main + prod_outputs + oidc_variables + oidc_outputs,
        [
            "preview_role_name = var.github_preview_role_name",
            'output "github_preview_deploy_role_arn"',
            'output "preview_lambda_permissions_boundary_arn"',
            'output "preview_lambda_execution_role_arn"',
        ],
    ) or not re.search(
        r'default\s*=\s*"arte-chatbot-preview-github-deploy"',
        preview_role_variable,
    ):
        findings.append(
            "production foundation must expose reproducible preview role and boundary outputs"
        )

    return findings


def _check_lambda_backend_module(
    lambda_main: str, lambda_variables: str, lambda_outputs: str
) -> list[str]:
    findings: list[str] = []

    required_resources = [
        'resource "aws_lambda_function" "this"',
        'resource "aws_lambda_alias" "this"',
        'resource "aws_iam_role" "lambda"',
        'resource "aws_cloudwatch_log_group" "lambda"',
        'resource "aws_dynamodb_table" "state"',
        'resource "aws_apigatewayv2_api" "this"',
        'resource "aws_apigatewayv2_integration" "lambda"',
        'resource "aws_lambda_permission" "allow_http_api"',
    ]
    if not _contains_all(lambda_main, required_resources):
        findings.append(
            "lambda_backend module must declare Lambda, alias, IAM, logs, DynamoDB, HTTP API, and invoke permission"
        )

    if any(
        token in lambda_main for token in ["vpc_config", "aws_nat_gateway", "aws_eip"]
    ):
        findings.append(
            "lambda_backend module must not attach Lambda to a VPC or require NAT"
        )

    required_iam = [
        "s3:GetObject",
        "s3:ListBucket",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "ssm:GetParameter",
        "secretsmanager:GetSecretValue",
    ]
    if not _contains_all(lambda_main, required_iam):
        findings.append(
            "lambda_backend IAM policy must allow scoped S3, DynamoDB, SSM, and Secrets Manager access"
        )

    if any(
        token in lambda_main + lambda_variables
        for token in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", ".env.deploy"]
    ):
        findings.append(
            "lambda_backend must not wire static AWS credentials or .env.deploy"
        )

    if (
        "validation {" not in _variable_block(lambda_variables, "runtime_secret_arns")
        or 'startswith(arn, "arn:")' not in lambda_variables
    ):
        findings.append(
            "lambda_backend runtime_secret_arns must reject plaintext secret values"
        )

    if 'default     = "python3.12"' not in _variable_block(lambda_variables, "runtime"):
        findings.append(
            "lambda_backend runtime must be python3.12 for package compatibility"
        )

    if not _contains_all(
        lambda_outputs,
        [
            'output "function_name"',
            'output "alias_arn"',
            'output "published_version"',
            'output "state_table_name"',
            'output "invoke_url"',
        ],
    ):
        findings.append(
            "lambda_backend outputs must expose Lambda, alias, version, state table, and direct endpoint metadata"
        )

    return findings


def _check_local_staging_lambda(
    local_staging_main: str, local_staging_variables: str, local_staging_outputs: str
) -> list[str]:
    findings: list[str] = []

    lambda_module = _module_block(local_staging_main, "lambda_backend")
    if not lambda_module or not _contains_all(
        lambda_module,
        [
            'source = "../../modules/lambda_backend"',
            "local.lambda_name",
            "local-staging#${var.staging_id}",
            'alias_name           = "staging"',
            'SECRET_NAMESPACE = "/arte-chatbot/local-staging/${var.staging_id}/"',
        ],
    ):
        findings.append(
            "local staging must wire an isolated lambda_backend module with staging alias, state prefix, and secret namespace"
        )

    if (
        "aws_bucket_name" not in local_staging_variables
        or "rejects production S3 buckets" not in local_staging_variables
    ):
        findings.append("local staging must reject production S3 buckets by default")

    if (
        'strcontains(lower(arn), "local-staging")' not in local_staging_variables
        or 'strcontains(lower(arn), "staging")' not in local_staging_variables
    ):
        findings.append(
            "local staging secret ARNs must be staging/local-staging scoped"
        )

    if not _contains_all(
        local_staging_main, ["ExpiresAt", "CleanupAfter", "var.expiration_at"]
    ):
        findings.append(
            "local staging must tag resources with expiration cleanup metadata"
        )

    if (
        'output "lambda_backend"' not in local_staging_outputs
        or "invoke_url" not in local_staging_outputs
    ):
        findings.append(
            "local staging outputs must expose the direct Lambda HTTP API endpoint"
        )

    return findings


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)


def _output_block_is_sensitive(text: str, output_name: str) -> bool:
    pattern = re.compile(
        rf'output\s+"{re.escape(output_name)}"\s+{{(?P<body>.*?)\n}}', re.DOTALL
    )
    match = pattern.search(text)
    return bool(match and re.search(r"sensitive\s*=\s*true", match.group("body")))


def _variable_block(text: str, variable_name: str) -> str:
    pattern = re.compile(
        rf'variable\s+"{re.escape(variable_name)}"\s+{{(?P<body>.*?)\n}}', re.DOTALL
    )
    match = pattern.search(text)
    return match.group(0) if match else ""


def _module_block(text: str, module_name: str) -> str:
    pattern = re.compile(
        rf'module\s+"{re.escape(module_name)}"\s+{{(?P<body>.*?)\n}}', re.DOTALL
    )
    match = pattern.search(text)
    return match.group(0) if match else ""


def _data_block(text: str, data_type: str, data_name: str) -> str:
    pattern = re.compile(
        rf'data\s+"{re.escape(data_type)}"\s+"{re.escape(data_name)}"\s+{{(?P<body>.*?)(?=\ndata\s+"|\nresource\s+"|\Z)',
        re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(0) if match else ""
