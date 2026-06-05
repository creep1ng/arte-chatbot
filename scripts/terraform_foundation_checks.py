"""Static validation checks for the Terraform foundation scaffold.

These checks intentionally inspect repository files without requiring Terraform
provider initialization, so they are safe for PR validation and local TDD cycles.
"""

from pathlib import Path
import re


TERRAFORM_ROOT = Path("infra/terraform")
PROD_ROOT = TERRAFORM_ROOT / "envs" / "prod"
MODULE_ROOT = TERRAFORM_ROOT / "modules"


def check_foundation(project_root: Path) -> list[str]:
    """Return validation finding messages for the Terraform foundation scaffold."""
    findings: list[str] = []

    prod_main = _read(project_root / PROD_ROOT / "main.tf")
    prod_variables = _read(project_root / PROD_ROOT / "variables.tf")
    prod_outputs = _read(project_root / PROD_ROOT / "outputs.tf")
    tunnel_variables = _read(project_root / MODULE_ROOT / "cloudflare_tunnel" / "variables.tf")
    tunnel_outputs = _read(project_root / MODULE_ROOT / "cloudflare_tunnel" / "outputs.tf")
    secrets_outputs = _read(project_root / MODULE_ROOT / "ssm_secrets" / "outputs.tf")
    admin_dockerfile = _read(project_root / "admin" / "Dockerfile")
    admin_nginx = _read(project_root / "admin" / "nginx.conf")

    if 'module "edge_tunnel"' not in prod_main:
        findings.append("prod must declare one central edge tunnel")

    if "http://backend:8000" not in prod_main or "var.backend_hostname" not in prod_main:
        findings.append("backend route must target Compose DNS origin backend:8000")
    if "http://frontend:3000" not in prod_main or "var.frontend_hostname" not in prod_main:
        findings.append("frontend route must target Compose DNS origin frontend:3000")
    if "http://admin:3000" not in prod_main or "var.admin_hostname" not in prod_main:
        findings.append("admin route must target Compose DNS origin admin:3000")

    if "central_connector_mode" not in tunnel_variables or "distinct" not in tunnel_variables:
        findings.append("cloudflare tunnel module must reject mixed localhost origins")

    if "central_connector_mode = true" not in prod_main:
        findings.append("prod central tunnel must enable central connector mode")

    if not _output_block_is_sensitive(tunnel_outputs, "tunnel_token"):
        findings.append("cloudflare tunnel token output must be sensitive")

    secret_outputs = ["secret_arns", "ssm_parameter_arns"]
    if any(not _output_block_is_sensitive(secrets_outputs, output) for output in secret_outputs):
        findings.append("secret value outputs must be sensitive")

    if "tunnel_token" in prod_outputs.lower():
        findings.append("prod outputs must not expose tunnel tokens")

    hostname_variables = [
        _variable_block(prod_variables, "backend_hostname"),
        _variable_block(prod_variables, "frontend_hostname"),
        _variable_block(prod_variables, "admin_hostname"),
    ]
    if any(not block or "sensitive   = true" not in block or re.search(r"(?m)^\s*default\s*=", block) for block in hostname_variables):
        findings.append("prod hostname variables must be sensitive inputs without defaults")

    if "hostname_labels" in prod_main or "var.domain_name" in prod_main:
        findings.append("prod hostnames must not derive chatbot, app, and admin from domain_name")

    if "staging" not in prod_variables or "strcontains" not in prod_variables:
        findings.append("prod name prefix must reject staging values")

    if not admin_dockerfile:
        findings.append("admin Dockerfile must exist")
    if "listen 3000" not in admin_nginx:
        findings.append("admin nginx config must listen on port 3000")
    if "COPY admin/" not in admin_dockerfile or "COPY frontend/" in admin_dockerfile:
        findings.append("admin image must copy admin source, not frontend source")

    return findings


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)


def _output_block_is_sensitive(text: str, output_name: str) -> bool:
    pattern = re.compile(rf'output\s+"{re.escape(output_name)}"\s+{{(?P<body>.*?)\n}}', re.DOTALL)
    match = pattern.search(text)
    return bool(match and re.search(r"sensitive\s*=\s*true", match.group("body")))


def _variable_block(text: str, variable_name: str) -> str:
    pattern = re.compile(rf'variable\s+"{re.escape(variable_name)}"\s+{{(?P<body>.*?)\n}}', re.DOTALL)
    match = pattern.search(text)
    return match.group(0) if match else ""
