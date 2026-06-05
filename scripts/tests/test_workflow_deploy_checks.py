"""Static checks for the EC2 Compose production deploy workflow."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workflow_deploy_checks import check_workflow_deploy


ROOT = Path(__file__).resolve().parents[2]


def _findings() -> list[str]:
    return check_workflow_deploy(ROOT)


def test_workflow_keeps_production_deploys_on_main_after_ci_health_and_evaluation() -> None:
    """PRs must not deploy; main deploy waits for successful CI, health, and evaluation."""
    findings = _findings()

    assert "production deploy job must run only on push events to refs/heads/main" not in findings
    assert "production deploy job must depend on release image promotion after evaluation gates" not in findings
    assert "pull requests must not have any production deploy path" not in findings


def test_workflow_passes_external_hostnames_and_runtime_env_without_hardcoding() -> None:
    """Deploy inputs must come from Secrets/Variables, not committed hostname defaults."""
    findings = _findings()

    assert "production deploy must pass backend/frontend/admin hostnames from secrets" not in findings
    assert "production deploy must not hardcode service hostnames in workflow source" not in findings
    assert "production deploy must pass backend runtime env from vars with {} fallback" not in findings
    assert "production deploy must keep backend secrets in runtime secret ARNs" not in findings


def test_workflow_uses_sha_ecr_tags_and_ssm_compose_deploy_instead_of_ecs() -> None:
    """Main deploy must invoke the EC2 Compose host deploy script through SSM."""
    findings = _findings()

    assert "production deploy must keep SHA-tagged ECR release images" not in findings
    assert "production deploy must invoke /opt/arte-chatbot/deploy.sh through SSM" not in findings
    assert "production deploy must not keep ECS service update paths" not in findings


def test_workflow_runs_cloudflare_backend_health_check_after_ssm_deploy() -> None:
    """The deploy job must prove the public backend URL is healthy after SSM completes."""
    findings = _findings()

    assert "production deploy must verify backend health through the Cloudflare hostname" not in findings
