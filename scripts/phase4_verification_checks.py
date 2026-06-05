"""Static checks for Phase 4 verification and setup evidence.

These checks intentionally avoid live AWS, Cloudflare, Docker, and Terraform plan
execution. They validate the local evidence that can be produced safely in this
slice and require apply progress to record live-validation limitations.
"""

from pathlib import Path
import re


PROD_ROOT = Path("infra/terraform/envs/prod")
COMPOSE_ROOT = Path("infra/terraform/modules/ec2_compose_host")
WORKFLOW_PATH = Path(".github/workflows/ci.yml")
APPLY_PROGRESS_PATH = Path("openspec/changes/low-cost-ec2-compose-exposure/apply-progress.md")


def check_phase4_verification_evidence(project_root: Path) -> list[str]:
    """Return static findings for Phase 4 verification evidence."""
    prod_main = _read(project_root / PROD_ROOT / "main.tf")
    prod_variables = _read(project_root / PROD_ROOT / "variables.tf")
    deploy_template = _read(project_root / COMPOSE_ROOT / "templates" / "deploy.sh.tftpl")
    workflow = _read(project_root / WORKFLOW_PATH)
    apply_progress = _read(project_root / APPLY_PROGRESS_PATH)

    findings: list[str] = []
    findings.extend(_check_ami_evidence(prod_main, prod_variables))
    findings.extend(_check_hostname_evidence(prod_main, prod_variables, apply_progress))
    findings.extend(_check_runtime_deploy_evidence(prod_variables, deploy_template, workflow))
    findings.extend(_check_live_limitations(apply_progress))
    return findings


def _check_ami_evidence(prod_main: str, prod_variables: str) -> list[str]:
    ami_block = _block(prod_main, "data", "aws_ami", "ubuntu_lts")
    override_block = _block(prod_variables, "variable", "ami_id_override")
    has_dynamic_lts = _contains_all(
        ami_block,
        [
            "most_recent = true",
            'owners      = ["099720109477"]',
            "ubuntu/images/hvm-ssd/ubuntu-*-amd64-server-*",
            'values = ["hvm"]',
            'values = ["ebs"]',
        ],
    )
    has_override = "default     = null" in override_block
    has_resolution = "coalesce(var.ami_id_override, data.aws_ami.ubuntu_lts.id)" in prod_main
    has_fixed_ami_default = bool(re.search(r'default\s*=\s*"ami-[a-zA-Z0-9]+"', prod_variables))

    if not has_dynamic_lts or not has_override or not has_resolution or has_fixed_ami_default:
        return ["phase4 must prove Ubuntu LTS AMI data-source default with optional override"]
    return []


def _check_hostname_evidence(prod_main: str, prod_variables: str, apply_progress: str) -> list[str]:
    hostname_variables = [
        _block(prod_variables, "variable", "backend_hostname"),
        _block(prod_variables, "variable", "frontend_hostname"),
        _block(prod_variables, "variable", "admin_hostname"),
    ]
    has_sensitive_inputs = all(
        block and "sensitive   = true" in block and not re.search(r"(?m)^\s*default\s*=", block)
        for block in hostname_variables
    )
    has_variable_routes = _contains_all(
        prod_main,
        [
            "hostname         = var.backend_hostname",
            "hostname         = var.frontend_hostname",
            "hostname         = var.admin_hostname",
        ],
    )
    documents_dns_visibility = "DNS records may become public" in apply_progress

    if not has_sensitive_inputs or not has_variable_routes or not documents_dns_visibility:
        return ["phase4 must prove service hostnames have no repo defaults and DNS visibility is public by design"]
    return []


def _check_runtime_deploy_evidence(prod_variables: str, deploy_template: str, workflow: str) -> list[str]:
    runtime_block = _block(prod_variables, "variable", "backend_runtime_environment_variables")
    has_runtime_map = "type        = map(string)" in runtime_block and "default     = {}" in runtime_block
    has_secret_refs = 'variable "backend_runtime_secret_arns"' in prod_variables
    has_ssm_deploy = _contains_all(
        workflow,
        [
            "aws ssm send-command",
            "/opt/arte-chatbot/deploy.sh ${SHA_TAG}",
            "aws ssm wait command-executed",
            "aws ssm get-command-invocation",
        ],
    )
    has_health_and_rollback = _contains_all(
        deploy_template,
        [
            "PREVIOUS_TAG_FILE",
            "docker compose --project-directory \"$PROJECT_DIR\" up -d --remove-orphans",
            "curl -fsS --retry 12 --retry-delay 5 http://127.0.0.1:8000/health",
        ],
    )

    if not has_runtime_map or not has_secret_refs or not has_ssm_deploy or not has_health_and_rollback:
        return ["phase4 must prove runtime env map, SSM deploy, compose health, and rollback metadata"]
    return []


def _check_live_limitations(apply_progress: str) -> list[str]:
    required_limitations = [
        "terraform plan was not run because live AWS/Cloudflare credentials and production secrets are not available",
        "SSM Run Command, `docker compose ps`, Cloudflare URL health, and Fargate rollback execution require the live production environment",
    ]
    if not _contains_all(apply_progress, required_limitations):
        return ["phase4 must explicitly document missing live AWS/Cloudflare credential limitations"]
    return []


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
