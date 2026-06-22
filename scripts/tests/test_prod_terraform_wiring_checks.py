"""Static checks for Lambda-only production Terraform wiring."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prod_terraform_wiring_checks import check_prod_terraform_wiring


ROOT = Path(__file__).resolve().parents[2]


def _findings() -> list[str]:
    return check_prod_terraform_wiring(ROOT)


def test_prod_removes_ec2_compose_cloudflare_tunnel_and_vpc_inputs() -> None:
    """Prod root must plan Lambda-only without legacy EC2/Tunnel variables."""
    findings = _findings()

    assert (
        "prod must remove EC2 Compose, Cloudflare Tunnel, VPC/subnet inputs, and obsolete outputs"
        not in findings
    )
    assert (
        "prod provider set must not require Cloudflare for Lambda-only apply"
        not in findings
    )


def test_prod_keeps_external_hostnames_and_sensitive_public_outputs() -> None:
    """Hostnames remain externally supplied but no longer require Cloudflare Tunnel."""
    findings = _findings()

    assert (
        "prod hostname variables must be sensitive inputs without defaults"
        not in findings
    )
    assert (
        "prod must not derive service hostnames from hardcoded chatbot/app/admin labels"
        not in findings
    )
    assert "prod public URL outputs must remain sensitive" not in findings


def test_prod_wires_lambda_backend_as_only_backend_target() -> None:
    """Production must expose Lambda/API Gateway/DynamoDB metadata and no EC2 fallback."""
    findings = _findings()

    assert (
        "prod must wire Lambda/API Gateway/DynamoDB as the only backend target"
        not in findings
    )
    assert (
        "prod Lambda backend wiring must not pass VPC, subnet, security group, or NAT inputs"
        not in findings
    )
    assert (
        "prod variables must expose Lambda package, sizing, runtime env, secrets, and state TTL inputs"
        not in findings
    )
    assert "prod runtime environment variables must stay a string map" not in findings
    assert (
        "prod must reject raw secret values in backend_runtime_secret_arns"
        not in findings
    )
    assert (
        "prod outputs must expose Lambda version, API endpoint, state table, and role metadata"
        not in findings
    )


def test_prod_deploy_role_uses_lambda_scopes_not_ec2_ssm() -> None:
    """Optional prod OIDC role must scope Lambda promotion, not EC2 Run Command."""
    findings = _findings()

    assert (
        "github OIDC module must not require ECS permissions for Lambda-only deploys"
        not in findings
    )
    assert (
        "prod deploy role must not target EC2 instances or SSM Run Command"
        not in findings
    )
    assert (
        "prod deploy role must receive Lambda, DynamoDB state, and runtime secret scopes"
        not in findings
    )
    assert (
        "github OIDC module must allow scoped Lambda promotion and state smoke reads"
        not in findings
    )
