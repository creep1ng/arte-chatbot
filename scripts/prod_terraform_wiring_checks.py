"""Static checks for Lambda-only production Terraform wiring.

These checks inspect repository files only. They keep the destructive Lambda
cutover verifiable without requiring AWS, Cloudflare, or Terraform credentials.
"""

from pathlib import Path
import re


PROD_ROOT = Path("infra/terraform/envs/prod")
GITHUB_OIDC_ROOT = Path("infra/terraform/modules/github_oidc")


REMOVED_PROD_TOKENS = [
    'variable "vpc_id"',
    'variable "public_subnet_id"',
    'variable "edge_tunnel_secret"',
    'variable "cloudflare_account_id"',
    'variable "ec2_compose_instance_type"',
    'variable "ami_id_override"',
    'module "compose_host"',
    'module "edge_tunnel"',
    'module "cloudflare_tunnel_secrets"',
    'data "aws_ami" "ubuntu_lts"',
    'output "ec2_compose_host"',
    'output "edge_tunnel"',
    "AWS-RunShellScript",
    "ssm_instance_arns =",
    "ssm_document_arns =",
]


def check_prod_terraform_wiring(project_root: Path) -> list[str]:
    """Return validation finding messages for production Terraform wiring."""
    findings: list[str] = []

    prod_main = _read(project_root / PROD_ROOT / "main.tf")
    prod_variables = _read(project_root / PROD_ROOT / "variables.tf")
    prod_outputs = _read(project_root / PROD_ROOT / "outputs.tf")
    prod_providers = _read(project_root / PROD_ROOT / "providers.tf")
    github_main = _read(project_root / GITHUB_OIDC_ROOT / "main.tf")
    github_variables = _read(project_root / GITHUB_OIDC_ROOT / "variables.tf")

    findings.extend(
        _check_removed_ec2_cloudflare_wiring(
            prod_main,
            prod_variables,
            prod_outputs,
            prod_providers,
        )
    )
    findings.extend(_check_prod_hostnames(prod_main, prod_variables, prod_outputs))
    findings.extend(_check_prod_lambda_wiring(prod_main, prod_variables, prod_outputs))
    findings.extend(
        _check_github_oidc_lambda_deploy(prod_main, github_main, github_variables)
    )

    return findings


def _check_removed_ec2_cloudflare_wiring(
    prod_main: str,
    prod_variables: str,
    prod_outputs: str,
    prod_providers: str,
) -> list[str]:
    combined = "\n".join([prod_main, prod_variables, prod_outputs, prod_providers])
    if any(token in combined for token in REMOVED_PROD_TOKENS):
        return [
            "prod must remove EC2 Compose, Cloudflare Tunnel, VPC/subnet inputs, and obsolete outputs"
        ]

    return []


def _check_prod_hostnames(
    prod_main: str, prod_variables: str, prod_outputs: str
) -> list[str]:
    findings: list[str] = []
    hostname_names = ["backend_hostname", "frontend_hostname", "admin_hostname"]
    hostname_blocks = [
        _block(prod_variables, "variable", name) for name in hostname_names
    ]

    if any(
        not block
        or "sensitive   = true" not in block
        or re.search(r"(?m)^\s*default\s*=", block)
        for block in hostname_blocks
    ):
        findings.append(
            "prod hostname variables must be sensitive inputs without defaults"
        )

    if "hostname_labels" in prod_main or any(
        label in prod_main for label in ['= "chatbot"', '= "app"', '= "admin"']
    ):
        findings.append(
            "prod must not derive service hostnames from hardcoded chatbot/app/admin labels"
        )

    if (
        'output "public_urls"' not in prod_outputs
        or "sensitive = true" not in prod_outputs
    ):
        findings.append("prod public URL outputs must remain sensitive")

    return findings


def _check_prod_lambda_wiring(
    prod_main: str, prod_variables: str, prod_outputs: str
) -> list[str]:
    findings: list[str] = []

    lambda_module = _block(prod_main, "module", "lambda_backend")
    if not lambda_module or not _contains_all(
        lambda_module,
        [
            'source = "../../modules/lambda_backend"',
            "local.lambda_name",
            'state_key_prefix                           = "prod"',
            'alias_name           = "live"',
            "public_api_url       = local.public_api_url",
            "runtime_secret_arns           = var.backend_runtime_secret_arns",
        ],
    ):
        findings.append(
            "prod must wire Lambda/API Gateway/DynamoDB as the only backend target"
        )

    if any(
        token in lambda_module
        for token in ["vpc_id", "subnet", "security_group", "vpc_config", "nat_gateway"]
    ):
        findings.append(
            "prod Lambda backend wiring must not pass VPC, subnet, security group, or NAT inputs"
        )

    required_variables = [
        'variable "lambda_package_path"',
        'variable "lambda_memory_size"',
        'variable "lambda_timeout_seconds"',
        'variable "lambda_session_ttl_seconds"',
        'variable "backend_runtime_environment_variables"',
        'variable "backend_runtime_secret_arns"',
        'variable "kms_key_arns"',
    ]
    if not _contains_all(prod_variables, required_variables):
        findings.append(
            "prod variables must expose Lambda package, sizing, runtime env, secrets, and state TTL inputs"
        )

    runtime_env = _block(
        prod_variables,
        "variable",
        "backend_runtime_environment_variables",
    )
    if "type        = map(string)" not in runtime_env:
        findings.append("prod runtime environment variables must stay a string map")

    runtime_secret_arns = _block(
        prod_variables, "variable", "backend_runtime_secret_arns"
    )
    if 'startswith(value, "arn:")' not in runtime_secret_arns:
        findings.append(
            "prod must reject raw secret values in backend_runtime_secret_arns"
        )

    if 'output "lambda_backend"' not in prod_outputs or not _contains_all(
        prod_outputs,
        [
            "published_version",
            "http_api_id",
            "invoke_url",
            "state_table_name",
            "role_arn",
        ],
    ):
        findings.append(
            "prod outputs must expose Lambda version, API endpoint, state table, and role metadata"
        )

    return findings


def _check_github_oidc_lambda_deploy(
    prod_main: str,
    github_main: str,
    github_variables: str,
) -> list[str]:
    findings: list[str] = []
    combined_github = github_main + github_variables

    if any(
        token in combined_github
        for token in [
            "ecs:",
            "ecs_cluster_arn",
            "ecs_service_arns",
            "pass_role_arns",
        ]
    ):
        findings.append(
            "github OIDC module must not require ECS permissions for Lambda-only deploys"
        )

    if "ssm_instance_arns =" in prod_main or "ssm_document_arns =" in prod_main:
        findings.append(
            "prod deploy role must not target EC2 instances or SSM Run Command"
        )

    if not _contains_all(
        prod_main,
        [
            "lambda_function_arns = [module.lambda_backend.function_arn]",
            "lambda_alias_arns    = [module.lambda_backend.alias_arn]",
            "state_table_arns     = [module.lambda_backend.state_table_arn]",
            "secret_arns          = values(var.backend_runtime_secret_arns)",
        ],
    ):
        findings.append(
            "prod deploy role must receive Lambda, DynamoDB state, and runtime secret scopes"
        )

    if not _contains_all(
        combined_github,
        [
            'variable "lambda_function_arns"',
            'variable "lambda_alias_arns"',
            'variable "state_table_arns"',
            "LambdaPackagePromotion",
            "lambda:UpdateFunctionCode",
            "lambda:UpdateAlias",
            "ReadSmokeStateTable",
            "dynamodb:Query",
        ],
    ):
        findings.append(
            "github OIDC module must allow scoped Lambda promotion and state smoke reads"
        )

    return findings


def _block(text: str, kind: str, *labels: str) -> str:
    quoted_labels = "".join(rf'\s+"{re.escape(label)}"' for label in labels)
    pattern = re.compile(rf"{kind}{quoted_labels}\s+{{(?P<body>.*?)\n}}", re.DOTALL)
    match = pattern.search(text)
    return match.group(0) if match else ""


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)
