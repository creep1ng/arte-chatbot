"""Validation tests for the PR2 Terraform foundation work unit."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terraform_foundation_checks import check_foundation


ROOT = Path(__file__).resolve().parents[2]


def _findings() -> list[str]:
    return check_foundation(ROOT)


def test_prod_uses_central_cloudflare_tunnel_and_compose_origins() -> None:
    """Production must use one central tunnel reaching Compose DNS origins."""
    findings = _findings()

    assert "prod must declare one central edge tunnel" not in findings
    assert "backend route must target Compose DNS origin backend:8000" not in findings
    assert "frontend route must target Compose DNS origin frontend:3000" not in findings
    assert "admin route must target Compose DNS origin admin:3000" not in findings


def test_central_connector_mode_allows_reachable_mixed_origins() -> None:
    """Mixed origins are allowed only for explicit central connector mode."""
    findings = _findings()

    assert "cloudflare tunnel module must reject mixed localhost origins" not in findings
    assert "prod central tunnel must enable central connector mode" not in findings


def test_tunnel_tokens_and_secret_outputs_are_sensitive() -> None:
    """Cloudflare tunnel token material must not be exposed through plaintext outputs."""
    findings = _findings()

    assert "cloudflare tunnel token output must be sensitive" not in findings
    assert "secret value outputs must be sensitive" not in findings
    assert "prod outputs must not expose tunnel tokens" not in findings


def test_prod_hostnames_are_external_and_name_is_isolated_from_staging() -> None:
    """Prod root must use external sensitive hostnames without staging names."""
    findings = _findings()

    assert "prod hostname variables must be sensitive inputs without defaults" not in findings
    assert "prod hostnames must not derive chatbot, app, and admin from domain_name" not in findings
    assert "prod name prefix must reject staging values" not in findings


def test_admin_scaffold_is_a_separate_image() -> None:
    """Admin must be an independent container image/service, not a frontend route."""
    findings = _findings()

    assert "admin Dockerfile must exist" not in findings
    assert "admin nginx config must listen on port 3000" not in findings
    assert "admin image must copy admin source, not frontend source" not in findings
