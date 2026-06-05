"""Static checks for the EC2 Compose host Terraform module.

These checks inspect repository files only. They are intentionally lightweight so
the first chained PR can validate the module contract without AWS, Cloudflare, or
Terraform credentials.
"""

from pathlib import Path
import re


MODULE_ROOT = Path("infra/terraform/modules/ec2_compose_host")
COMPOSE_TEMPLATE = MODULE_ROOT / "templates" / "docker-compose.yml.tftpl"
DEPLOY_TEMPLATE = MODULE_ROOT / "templates" / "deploy.sh.tftpl"


def check_ec2_compose_module(project_root: Path) -> list[str]:
    """Return validation finding messages for the EC2 Compose module."""
    findings: list[str] = []

    variables = _read(project_root / MODULE_ROOT / "variables.tf")
    outputs = _read(project_root / MODULE_ROOT / "outputs.tf")
    main = _read(project_root / MODULE_ROOT / "main.tf")
    compose = _read(project_root / COMPOSE_TEMPLATE)
    deploy = _read(project_root / DEPLOY_TEMPLATE)

    findings.extend(_check_compose_template(compose))
    findings.extend(_check_deploy_template(deploy))
    findings.extend(_check_module_contract(variables, outputs, main))

    return findings


def _check_compose_template(compose: str) -> list[str]:
    findings: list[str] = []

    if not _contains_all(compose, ["backend:", "frontend:", "admin:", "cloudflared:"]):
        findings.append("compose template must define backend, frontend, admin, and cloudflared services")

    compose_dns_origins = ["http://backend:8000", "http://frontend:3000", "http://admin:3000"]
    if not _contains_all(compose, compose_dns_origins) or "localhost" in compose:
        findings.append("cloudflared must route backend, frontend, and admin hostnames to Compose DNS origins")

    app_blocks = [_service_block(compose, service) for service in ("backend", "frontend", "admin")]
    if any(re.search(r"(?m)^\s+ports\s*:", block) for block in app_blocks):
        findings.append("backend, frontend, and admin services must not publish public ports")

    if "http_status:404" not in compose:
        findings.append("cloudflared ingress must include a 404 fallback")

    return findings


def _check_deploy_template(deploy: str) -> list[str]:
    findings: list[str] = []

    if "sha-*" not in deploy or "usage: deploy.sh <sha-tag>" not in deploy:
        findings.append("deploy template must require a sha-* tag argument")

    if not _contains_all(deploy, ["previous-image-tag", "current-image-tag", "PREVIOUS_TAG"]):
        findings.append("deploy template must persist previous and current release tags")

    if not _contains_all(deploy, ["set -Eeuo pipefail", "compose", "pull", "up -d", "curl -fsS"]):
        findings.append("deploy template must fail on image pull, compose restart, or health check errors")

    return findings


def _check_module_contract(variables: str, outputs: str, main: str) -> list[str]:
    findings: list[str] = []

    required_variables = [
        'variable "subnet_id"',
        'variable "ami_id_override"',
        'variable "instance_type"',
        'variable "backend_image_uri"',
        'variable "frontend_image_uri"',
        'variable "admin_image_uri"',
        'variable "public_api_url"',
        'variable "public_frontend_url"',
        'variable "public_admin_url"',
        'variable "aws_bucket_name"',
        'variable "backend_runtime_secret_arns"',
        'variable "cloudflare_tunnel_token_secret_arn"',
        'variable "initial_image_tag"',
    ]
    if not _contains_all(variables, required_variables):
        findings.append("module variables must include subnet, optional AMI override, size, images, urls, bucket, secrets, tunnel token, and deploy metadata")

    required_outputs = ['output "instance_id"', 'output "instance_role_arn"', 'output "security_group_id"', 'output "deploy_script_path"']
    if not _contains_all(outputs, required_outputs) or "tunnel_token" in outputs.lower():
        findings.append("module outputs must expose host and deploy metadata without secret values")

    security_group_block = _resource_block(main, "aws_security_group", "this")
    if not security_group_block or "egress" not in security_group_block or re.search(r"(?m)^\s+ingress\s*{", security_group_block):
        findings.append("instance security group must be outbound-only with no ingress blocks")

    required_iam = ["AmazonSSMManagedInstanceCore", "ecr:GetAuthorizationToken", "s3:GetObject", "secretsmanager:GetSecretValue", "ssm:GetParameters"]
    if not _contains_all(main, required_iam):
        findings.append("instance role must allow SSM, ECR pull, S3 data access, and runtime secret reads")

    if not _contains_all(main, ["/opt/arte-chatbot", "docker-compose.yml", "deploy.sh"]):
        findings.append("bootstrap must install Docker Compose assets under /opt/arte-chatbot")

    return findings


def _service_block(compose: str, service: str) -> str:
    pattern = re.compile(rf"(?ms)^  {re.escape(service)}:\n(?P<body>(?:    .+\n|\n)+?)(?=^  [a-zA-Z0-9_-]+:|\Z)")
    match = pattern.search(compose)
    return match.group(0) if match else ""


def _resource_block(terraform: str, resource_type: str, name: str) -> str:
    pattern = re.compile(rf'resource\s+"{re.escape(resource_type)}"\s+"{re.escape(name)}"\s+{{(?P<body>.*?)\n}}', re.DOTALL)
    match = pattern.search(terraform)
    return match.group(0) if match else ""


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)
