"""Static checks for production Terraform EC2 Compose wiring.

These checks inspect repository files only. They keep the second chained PR slice
verifiable without requiring AWS, Cloudflare, or Terraform credentials.
"""

from pathlib import Path
import re


PROD_ROOT = Path("infra/terraform/envs/prod")
CLOUDFLARE_TUNNEL_ROOT = Path("infra/terraform/modules/cloudflare_tunnel")
GITHUB_OIDC_ROOT = Path("infra/terraform/modules/github_oidc")


def check_prod_terraform_wiring(project_root: Path) -> list[str]:
    """Return validation finding messages for production Terraform wiring."""
    findings: list[str] = []

    prod_main = _read(project_root / PROD_ROOT / "main.tf")
    prod_variables = _read(project_root / PROD_ROOT / "variables.tf")
    prod_outputs = _read(project_root / PROD_ROOT / "outputs.tf")
    tunnel_outputs = _read(project_root / CLOUDFLARE_TUNNEL_ROOT / "outputs.tf")
    github_main = _read(project_root / GITHUB_OIDC_ROOT / "main.tf")
    github_variables = _read(project_root / GITHUB_OIDC_ROOT / "variables.tf")

    findings.extend(_check_ami_selection(prod_main, prod_variables))
    findings.extend(_check_hostnames_and_tunnel(prod_main, prod_variables, tunnel_outputs))
    findings.extend(_check_ec2_outputs_and_ssm(prod_main, prod_variables, prod_outputs, github_main, github_variables))

    return findings


def _check_ami_selection(prod_main: str, prod_variables: str) -> list[str]:
    findings: list[str] = []
    data_source = _block(prod_main, "data", "aws_ami", "ubuntu_lts")

    if not data_source or not _contains_all(
        data_source,
        [
            "most_recent = true",
            'owners      = ["099720109477"]',
            "ubuntu/images/hvm-ssd/ubuntu-*-amd64-server-*",
            'name   = "virtualization-type"',
            'values = ["hvm"]',
            'name   = "root-device-type"',
            'values = ["ebs"]',
        ],
    ):
        findings.append("prod must declare a Canonical latest Ubuntu LTS aws_ami data source")

    if "compose_host_ami_id = coalesce(var.ami_id_override, data.aws_ami.ubuntu_lts.id)" not in prod_main:
        findings.append("prod must resolve compose host AMI from ami_id_override or the Ubuntu LTS data source")

    ami_override = _block(prod_variables, "variable", "ami_id_override")
    fixed_ami_default = re.search(r'default\s*=\s*"ami-[a-zA-Z0-9]+"', prod_variables)
    if not ami_override or "default     = null" not in ami_override or fixed_ami_default:
        findings.append("prod must not commit fixed AMI id defaults")

    return findings


def _check_hostnames_and_tunnel(prod_main: str, prod_variables: str, tunnel_outputs: str) -> list[str]:
    findings: list[str] = []
    hostname_names = ["backend_hostname", "frontend_hostname", "admin_hostname"]
    hostname_blocks = [_block(prod_variables, "variable", name) for name in hostname_names]

    if any(not block or "sensitive   = true" not in block or re.search(r"(?m)^\s*default\s*=", block) for block in hostname_blocks):
        findings.append("prod hostname variables must be sensitive inputs without defaults")

    if "hostname_labels" in prod_main or any(label in prod_main for label in ['= "chatbot"', '= "app"', '= "admin"']):
        findings.append("prod must not derive service hostnames from hardcoded chatbot/app/admin labels")

    edge_tunnel = _block(prod_main, "module", "edge_tunnel")
    if not edge_tunnel or not _contains_all(
        edge_tunnel,
        [
            "central_connector_mode = true",
            "hostname         = var.backend_hostname",
            "hostname         = var.frontend_hostname",
            "hostname         = var.admin_hostname",
            'local_origin_url = "http://backend:8000"',
            'local_origin_url = "http://frontend:3000"',
            'local_origin_url = "http://admin:3000"',
        ],
    ):
        findings.append("prod must configure one central Cloudflare tunnel with Compose DNS origins")

    if any(name in prod_main for name in ["backend_cloudflare_tunnel", "frontend_cloudflare_tunnel", "admin_cloudflare_tunnel"]):
        findings.append("prod must not keep per-service production Cloudflare tunnels")

    if "ECS sidecar" in tunnel_outputs:
        findings.append("cloudflare tunnel module output wording must not be ECS-sidecar specific")

    return findings


def _check_ec2_outputs_and_ssm(
    prod_main: str,
    prod_variables: str,
    prod_outputs: str,
    github_main: str,
    github_variables: str,
) -> list[str]:
    findings: list[str] = []

    required_variables = [
        'variable "public_subnet_id"',
        'variable "ec2_compose_instance_type"',
        'variable "edge_tunnel_secret"',
        'variable "backend_runtime_environment_variables"',
        'variable "backend_runtime_secret_arns"',
        'variable "kms_key_arns"',
    ]
    if not _contains_all(prod_variables, required_variables) or 'type        = map(string)' not in _block(
        prod_variables,
        "variable",
        "backend_runtime_environment_variables",
    ):
        findings.append("prod variables must expose EC2 host inputs, one tunnel secret, runtime env map, and runtime secret refs")

    if 'module "compose_host"' not in prod_main or not _contains_all(
        prod_main,
        [
            'source = "../../modules/ec2_compose_host"',
            "ami_id            = local.compose_host_ami_id",
            "backend_image_uri  = module.backend_ecr.repository_url",
            "frontend_image_uri = module.frontend_ecr.repository_url",
            "admin_image_uri    = module.admin_ecr.repository_url",
            "backend_runtime_environment_variables = var.backend_runtime_environment_variables",
            "backend_runtime_secret_arns           = var.backend_runtime_secret_arns",
            "cloudflare_tunnel_token_secret_arn    = local.tunnel_token_secret_arns[\"edge_cloudflare_tunnel_token\"]",
        ],
    ):
        findings.append("prod must call the ec2_compose_host module with ECR images, URLs, env, secrets, and tunnel token secret")

    if not _contains_all(
        prod_outputs,
        [
            'output "ec2_compose_host"',
            "module.compose_host.instance_id",
            "module.compose_host.deploy_script_path",
            'output "public_urls"',
            "sensitive = true",
        ],
    ) or "ecs_services" in prod_outputs or "cluster_name" in prod_outputs:
        findings.append("prod outputs must expose EC2 deploy metadata and mark hostname-derived URLs sensitive")

    if any(token in github_main + github_variables for token in ["ecs:", "iam:PassRole", "ecs_cluster_arn", "ecs_service_arns", "pass_role_arns"]):
        findings.append("github OIDC module must use scoped SSM deploy permissions instead of ECS/pass-role permissions")
    elif not _contains_all(github_main + github_variables, ["ssm:SendCommand", "ssm:GetCommandInvocation", "ssm_instance_arns", "ssm_document_arns"]):
        findings.append("github OIDC module must use scoped SSM deploy permissions instead of ECS/pass-role permissions")

    return findings


def _block(text: str, kind: str, *labels: str) -> str:
    quoted_labels = "".join(rf'\s+"{re.escape(label)}"' for label in labels)
    pattern = re.compile(rf'{kind}{quoted_labels}\s+{{(?P<body>.*?)\n}}', re.DOTALL)
    match = pattern.search(text)
    return match.group(0) if match else ""


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)
