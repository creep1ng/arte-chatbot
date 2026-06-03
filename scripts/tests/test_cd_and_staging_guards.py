"""Validation tests for the PR3 CD workflow and local staging guardrails."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import os
import subprocess


import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deployment_guard_checks import check_cd_and_staging_guards


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "deploy-local-staging.sh"


def _findings() -> list[str]:
    return check_cd_and_staging_guards(ROOT)


def test_workflow_builds_all_images_and_pushes_sha_candidate_tags_after_gates() -> None:
    """PR candidates must be immutable SHA-visible tags and only publish after gates pass."""
    findings = _findings()

    assert "workflow must build backend, frontend, and admin images" not in findings
    assert "candidate image push must wait for test-health and evaluation gates" not in findings
    assert "candidate tags must include PR and SHA rollback identifiers" not in findings


def test_workflow_deploys_production_only_from_main_with_oidc() -> None:
    """Production deploys must be impossible on pull requests or non-main branches."""
    findings = _findings()

    assert "production deploy job must be gated to push events on refs/heads/main" not in findings
    assert "production deploy job must configure AWS credentials through OIDC" not in findings
    assert "production deploy job must provide Terraform AWS and Cloudflare inputs" not in findings
    assert "pull requests must not contain a production deploy job path" not in findings


def test_local_staging_root_is_isolated_and_rejects_production_mixing() -> None:
    """Local staging Terraform must use separate state, names, params, and hostnames."""
    findings = _findings()

    assert "local-staging Terraform root must exist" not in findings
    assert "local-staging must use isolated local backend state" not in findings
    assert "local-staging must derive unique staging hostnames from staging_id" not in findings
    assert "local-staging must reject production hostnames and names" not in findings
    assert "local-staging must isolate secret and parameter namespaces" not in findings


def test_deploy_script_rejects_ci_execution_without_calling_terraform() -> None:
    """CI must fail before Terraform can mutate AWS or Cloudflare resources."""
    result = subprocess.run(
        [str(SCRIPT), "--staging-id", "pr-123", "--backend-tag", "sha-abc1234", "--frontend-tag", "sha-abc1234", "--admin-tag", "sha-abc1234", "--plan-only"],
        cwd=ROOT,
        env={**os.environ, "CI": "true"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "local staging cannot run in CI" in result.stderr
    assert "terraform" not in result.stderr.lower()


def test_deploy_script_requires_explicit_tags_and_staging_id() -> None:
    """A staging deploy must never fall back to latest, bootstrap, or implicit tags."""
    result = subprocess.run(
        [str(SCRIPT), "--staging-id", "pr-123", "--backend-tag", "latest", "--frontend-tag", "sha-abc1234", "--admin-tag", "sha-abc1234", "--plan-only"],
        cwd=ROOT,
        env={k: v for k, v in os.environ.items() if k not in {"CI", "GITHUB_ACTIONS"}},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "backend tag must be an explicit immutable ECR tag" in result.stderr


def test_deploy_script_rejects_production_staging_ids() -> None:
    """Official production names/URLs must not be accepted as staging identifiers."""
    result = subprocess.run(
        [str(SCRIPT), "--staging-id", "api", "--backend-tag", "sha-abc1234", "--frontend-tag", "sha-abc1234", "--admin-tag", "sha-abc1234", "--plan-only"],
        cwd=ROOT,
        env={k: v for k, v in os.environ.items() if k not in {"CI", "GITHUB_ACTIONS"}},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "staging id would collide with production naming" in result.stderr


def test_deploy_script_rejects_expiration_after_three_days() -> None:
    """Expiration metadata must be no later than three days from creation."""
    too_late = (datetime.now(UTC) + timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%SZ")

    result = subprocess.run(
        [str(SCRIPT), "--staging-id", "pr-123", "--backend-tag", "sha-abc1234", "--frontend-tag", "sha-abc1234", "--admin-tag", "sha-abc1234", "--expires-at", too_late, "--plan-only"],
        cwd=ROOT,
        env={k: v for k, v in os.environ.items() if k not in {"CI", "GITHUB_ACTIONS"}},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "expiration must be no later than 3 days" in result.stderr


def test_deploy_script_fails_fast_when_deploy_inputs_are_missing() -> None:
    """Valid staging arguments still need explicit local Terraform/deploy inputs."""
    result = subprocess.run(
        [
            str(SCRIPT),
            "--staging-id",
            "pr-123",
            "--backend-tag",
            "sha-abc1234",
            "--frontend-tag",
            "sha-abc1234",
            "--admin-tag",
            "sha-abc1234",
            "--plan-only",
        ],
        cwd=ROOT,
        env={k: v for k, v in os.environ.items() if k not in {"CI", "GITHUB_ACTIONS", "TF_VAR_vpc_id"}},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "TF_VAR_vpc_id is required for local staging" in result.stderr
