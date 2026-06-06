"""Static checks for production Terraform EC2 Compose wiring."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prod_terraform_wiring_checks import check_prod_terraform_wiring


ROOT = Path(__file__).resolve().parents[2]


def _findings() -> list[str]:
    return check_prod_terraform_wiring(ROOT)


def test_prod_uses_dynamic_ubuntu_lts_ami_without_fixed_ami_defaults() -> None:
    """Production must resolve latest Ubuntu LTS by default with optional override only."""
    findings = _findings()

    assert "prod must declare a Canonical latest Ubuntu LTS aws_ami data source" not in findings
    assert "prod must resolve compose host AMI from ami_id_override or the Ubuntu LTS data source" not in findings
    assert "prod must not commit fixed AMI id defaults" not in findings


def test_prod_externalizes_hostnames_and_routes_single_central_tunnel() -> None:
    """Hostnames must be sensitive inputs and one tunnel must route Compose DNS origins."""
    findings = _findings()

    assert "prod hostname variables must be sensitive inputs without defaults" not in findings
    assert "prod must not derive service hostnames from hardcoded chatbot/app/admin labels" not in findings
    assert "prod must configure one central Cloudflare tunnel with Compose DNS origins" not in findings
    assert "prod must not keep per-service production Cloudflare tunnels" not in findings
    assert "cloudflare tunnel module output wording must not be ECS-sidecar specific" not in findings
    assert "cloudflare tunnel DNS for_each keys must unwrap externally supplied sensitive hostnames" not in findings


def test_prod_wires_ec2_compose_runtime_outputs_and_ssm_deploy_permissions() -> None:
    """EC2 host inputs, runtime env defaults, outputs, and deploy role must match Unit 2."""
    findings = _findings()

    assert "prod variables must expose EC2 host inputs, one tunnel secret, runtime env map, and runtime secret refs" not in findings
    assert "prod must reject raw secret values in backend_runtime_secret_arns" not in findings
    assert "prod must call the ec2_compose_host module with ECR images, URLs, env, secrets, and tunnel token secret" not in findings
    assert "prod outputs must expose EC2 deploy metadata and mark hostname-derived URLs sensitive" not in findings
    assert "github OIDC module must use scoped SSM deploy permissions instead of ECS/pass-role permissions" not in findings
