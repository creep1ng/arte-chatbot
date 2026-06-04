"""Validation tests for the PR2 Terraform foundation work unit."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terraform_foundation_checks import check_foundation


ROOT = Path(__file__).resolve().parents[2]


def _findings() -> list[str]:
    return check_foundation(ROOT)


def test_prod_uses_scoped_cloudflare_tunnels_and_local_origins() -> None:
    """Each public service must own a scoped tunnel reaching its same-task origin."""
    findings = _findings()

    assert "prod must declare backend, frontend, and admin scoped tunnels" not in findings
    assert "backend tunnel must route api hostname to localhost:8000" not in findings
    assert "frontend tunnel must route app hostname to localhost:3000" not in findings
    assert "admin tunnel must route admin hostname to localhost:3000" not in findings


def test_no_shared_unreachable_localhost_origins() -> None:
    """A tunnel must not mix backend and UI localhost origins in this Fargate layout."""
    findings = _findings()

    assert "cloudflare tunnel module must reject mixed localhost origins" not in findings
    assert "prod must not reuse one tunnel for backend, frontend, and admin" not in findings


def test_tunnel_tokens_and_secret_outputs_are_sensitive() -> None:
    """Cloudflare tunnel token material must not be exposed through plaintext outputs."""
    findings = _findings()

    assert "cloudflare tunnel token output must be sensitive" not in findings
    assert "secret value outputs must be sensitive" not in findings
    assert "prod outputs must not expose tunnel tokens" not in findings


def test_prod_names_and_domain_are_isolated_from_staging() -> None:
    """Prod root must keep Arte hostnames variable-driven without staging names."""
    findings = _findings()

    assert "prod domain must default to artesolutions.com.co" not in findings
    assert "prod hostnames must derive chatbot, app, and admin from domain_name" not in findings
    assert "prod name prefix must reject staging values" not in findings


def test_admin_scaffold_is_a_separate_image() -> None:
    """Admin must be an independent container image/service, not a frontend route."""
    findings = _findings()

    assert "admin Dockerfile must exist" not in findings
    assert "admin nginx config must listen on port 3000" not in findings
    assert "admin image must copy admin source, not frontend source" not in findings
