"""Static checks for the EC2 Compose host Terraform module."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ec2_compose_module_checks import check_ec2_compose_module


ROOT = Path(__file__).resolve().parents[2]


def _findings() -> list[str]:
    return check_ec2_compose_module(ROOT)


def test_compose_template_uses_internal_dns_without_public_ports() -> None:
    """Cloudflare must route to Compose DNS and app services must not publish ports."""
    findings = _findings()

    assert "compose template must define backend, frontend, admin, and cloudflared services" not in findings
    assert "cloudflared must route backend, frontend, and admin hostnames to Compose DNS origins" not in findings
    assert "backend, frontend, and admin services must not publish public ports" not in findings
    assert "cloudflared ingress must include a 404 fallback" not in findings


def test_deploy_template_requires_sha_tags_and_safe_rollback_metadata() -> None:
    """Deploy script must reject mutable tags and preserve previous tag metadata."""
    findings = _findings()

    assert "deploy template must require a sha-* tag argument" not in findings
    assert "deploy template must persist previous and current release tags" not in findings
    assert "deploy template must fail on image pull, compose restart, or health check errors" not in findings


def test_module_declares_host_inputs_outputs_and_outbound_only_security() -> None:
    """Module variables, outputs, and host security must support the first PR boundary."""
    findings = _findings()

    assert "module variables must include subnet, optional AMI override, size, images, urls, bucket, secrets, tunnel token, and deploy metadata" not in findings
    assert "module outputs must expose host and deploy metadata without secret values" not in findings
    assert "instance security group must be outbound-only with no ingress blocks" not in findings
    assert "instance role must allow SSM, ECR pull, S3 data access, and runtime secret reads" not in findings
    assert "bootstrap must install Docker Compose assets under /opt/arte-chatbot" not in findings
