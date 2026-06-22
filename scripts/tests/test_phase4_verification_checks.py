"""Static post-verification cleanup checks for Lambda-only production."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase4_verification_checks import check_phase4_verification_evidence


ROOT = Path(__file__).resolve().parents[2]


def _findings() -> list[str]:
    return check_phase4_verification_evidence(ROOT)


def test_phase4_cleanup_documents_lambda_runtime_and_custom_domain() -> None:
    """Docs and env examples must match Lambda/API Gateway/DynamoDB semantics."""
    findings = _findings()

    assert ".env.deploy must be ignored as local/manual deploy input" not in findings
    assert (
        ".env.example must document Lambda secret refs, execution role, "
        "DynamoDB state, and local .env.deploy semantics" not in findings
    )
    assert (
        ".env.example must not teach ECS production runtime semantics" not in findings
    )
    assert (
        "ADR-009 must distinguish Cloudflare DNS custom-domain inputs from "
        "retired Cloudflare Tunnel requirements" not in findings
    )
    assert (
        "deployment doc must not retain stale OpenAI 401 evidence after current deploy fix"
        not in findings
    )
    assert (
        "deployment doc must keep Lambda/custom-domain deployment semantics explicit"
        not in findings
    )


def test_phase4_cleanup_archives_legacy_openspec_artifacts() -> None:
    """Retired EC2/Fargate/Cloudflare artifacts must not remain active."""
    findings = _findings()

    assert "low-cost EC2 Compose OpenSpec change must be archived" not in findings
    assert "archived EC2 Compose change must include an archive report" not in findings
    assert (
        "fargate-cloudflare-ingress spec must be retired or historical, "
        "not active production Tunnel guidance" not in findings
    )
    assert (
        "runtime configuration spec must not describe ECS task role as "
        "current backend production runtime" not in findings
    )
    assert (
        "promotion spec must not describe ECS as the current backend "
        "production deployment path" not in findings
    )
    assert (
        "local staging spec must include current serverless staging isolation semantics"
        not in findings
    )
