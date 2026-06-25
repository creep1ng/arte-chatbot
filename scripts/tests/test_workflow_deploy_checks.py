"""Static checks for Lambda-only production deploy workflows."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workflow_deploy_checks import check_workflow_deploy


ROOT = Path(__file__).resolve().parents[2]


def _findings() -> list[str]:
    return check_workflow_deploy(ROOT)


def test_workflow_keeps_production_lambda_deploys_on_main_after_gates() -> None:
    """PRs must not deploy; production Lambda waits for package and cutover gates."""
    findings = _findings()

    assert (
        "production Lambda promotion job must run only on push events to refs/heads/main"
        not in findings
    )
    assert (
        "production Lambda smoke job must run only on push events to refs/heads/main"
        not in findings
    )
    assert (
        "production Lambda promotion must depend on package and cutover gates"
        not in findings
    )
    assert (
        "release image promotion must still wait for evaluation gates" not in findings
    )
    assert "pull requests must not have any production deploy path" not in findings


def test_workflow_uses_lambda_production_config_without_ec2_compose_path() -> None:
    """Production deploy config must be Lambda-only and avoid legacy EC2 inputs."""
    findings = _findings()

    assert (
        "production Lambda promotion must use Lambda function, alias, API, and state variables"
        not in findings
    )
    assert "production Lambda promotion must use AWS deploy role secret" not in findings
    assert (
        "production Lambda verification must smoke the API Gateway endpoint and DynamoDB state"
        not in findings
    )
    assert "legacy EC2 deploy-production job must be removed" not in findings
    assert (
        "workflow must not keep EC2 Compose, Cloudflare Tunnel, VPC/subnet, or revert-confirmation deploy paths"
        not in findings
    )


def test_lambda_package_job_tests_scans_and_uploads_same_package_artifact() -> None:
    """Lambda package promotion must start from one tested and scanned artifact."""
    findings = _findings()

    assert (
        "lambda package job must test, build, scan, and upload one zip artifact"
        not in findings
    )
    assert (
        "lambda package Python version must match Terraform Lambda runtime"
        not in findings
    )


def test_lambda_staging_deploy_and_smoke_validate_isolated_serverless_runtime() -> None:
    """Staging must deploy through OIDC and validate direct endpoint behavior."""
    findings = _findings()

    assert (
        "lambda staging deploy must use OIDC and the scanned package artifact"
        not in findings
    )
    assert (
        "lambda staging smoke must validate chat, File Inputs, DynamoDB, IAM denial, and URL isolation"
        not in findings
    )
    assert (
        "fixed Lambda staging deploy must be optional for main production cutover"
        not in findings
    )
    assert (
        "fixed Lambda staging smoke must run only after staging deploys" not in findings
    )
    assert (
        "production cutover must continue when fixed Lambda staging is disabled"
        not in findings
    )


def test_lambda_pr_preview_deploys_smokes_comments_and_cleans_up() -> None:
    """PR previews must be isolated, validated, discoverable, and disposable."""
    findings = _findings()

    assert (
        "lambda PR preview deploy must use the scanned package artifact and isolated Terraform state"
        not in findings
    )
    assert (
        "lambda PR preview smoke must validate the direct endpoint, state isolation, and evaluation harness"
        not in findings
    )
    assert "lambda PR preview must comment URL and validation result" not in findings
    assert (
        "lambda PR preview cleanup must destroy Terraform state on PR close"
        not in findings
    )


def test_lambda_production_cutover_is_lambda_only_and_promotes_same_package() -> None:
    """Production Lambda cutover must remove EC2 fallback and keep rollback target discovery."""
    findings = _findings()

    assert (
        "lambda cutover must verify production Terraform is Lambda-only" not in findings
    )
    assert (
        "lambda production promotion must use the same package and capture rollback target"
        not in findings
    )
    assert (
        "lambda rollback job must restore a discovered previous alias version"
        not in findings
    )
