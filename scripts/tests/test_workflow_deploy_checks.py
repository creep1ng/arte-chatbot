"""Static checks for Lambda-only production deploy workflows."""

from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workflow_deploy_checks import check_workflow_deploy


ROOT = Path(__file__).resolve().parents[2]
DETERMINISTIC_GATE_FINDING = "deterministic test job must run all Python test roots offline with fake credentials"
LAMBDA_GATE_FINDING = "lambda package job must depend on the deterministic test gate"
ROLLBACK_GUARD_FINDING = (
    "lambda rollback must require successful promotion, failed verification, and a "
    "non-empty target"
)
ROLLBACK_TARGET_FINDING = (
    "lambda rollback must skip safely when no target version exists"
)


def _findings() -> list[str]:
    return check_workflow_deploy(ROOT)


def _mutated_project(tmp_path: Path, old: str, new: str) -> Path:
    """Copy checked inputs and apply one mutation to the CI workflow."""
    checked_paths = [
        Path(".github/workflows/ci.yml"),
        Path(".github/workflows/lambda-preview-cleanup.yml"),
        Path(".python-version"),
        Path("infra/terraform/modules/lambda_backend/variables.tf"),
    ]
    for relative_path in checked_paths:
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative_path, destination)

    workflow_path = tmp_path / ".github/workflows/ci.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    assert old in workflow, f"mutation target is missing: {old}"
    workflow_path.write_text(workflow.replace(old, new, 1), encoding="utf-8")
    return tmp_path


def _mutated_checked_file(
    tmp_path: Path, relative_path: Path, old: str, new: str
) -> Path:
    """Copy checked inputs and mutate one workflow file."""
    project_root = _mutated_project(tmp_path, "name: CI", "name: CI")
    path = project_root / relative_path
    content = path.read_text(encoding="utf-8")
    assert old in content, f"mutation target is missing: {old}"
    path.write_text(content.replace(old, new, 1), encoding="utf-8")
    return project_root


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


def test_deterministic_suites_gate_lambda_packaging() -> None:
    """All deterministic roots must run offline before packaging starts."""
    findings = _findings()

    assert DETERMINISTIC_GATE_FINDING not in findings
    assert LAMBDA_GATE_FINDING not in findings


@pytest.mark.parametrize(
    "test_root",
    ["backend/tests", "backend/app/tests", "rag/tests"],
)
def test_deterministic_gate_rejects_an_omitted_test_root(
    tmp_path: Path, test_root: str
) -> None:
    """Removing any required test root must break the static CI guard."""
    project_root = _mutated_project(tmp_path, f" {test_root}", "")

    assert DETERMINISTIC_GATE_FINDING in check_workflow_deploy(project_root)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param('-m "not live"', "", id="missing-live-filter"),
        pytest.param(
            "backend/tests backend/app/tests",
            "backend/tests/test_config.py backend/app/tests",
            id="root-prefix-substitution",
        ),
        pytest.param('-m "not live"', '# -m "not live"', id="commented-live-filter"),
        pytest.param(
            "      OPENAI_API_KEY: test-openai-key",
            "      # OPENAI_API_KEY: test-openai-key",
            id="commented-fake-environment",
        ),
        pytest.param(
            "run: uv run pytest backend/tests",
            "run: echo uv run pytest backend/tests",
            id="echo-wrapper",
        ),
        pytest.param(
            '        run: uv run pytest backend/tests backend/app/tests rag/tests evaluation/tests evaluation/harness/tests evaluation/context_budget -m "not live"',
            "        run: |\n"
            "          uv run pytest backend/tests backend/app/tests rag/tests evaluation/tests evaluation/harness/tests evaluation/context_budget "
            '-m "not live"\n'
            "          uv run pytest backend/tests backend/app/tests rag/tests evaluation/tests evaluation/harness/tests evaluation/context_budget "
            '-m "not live"',
            id="multiple-pytest-commands",
        ),
        pytest.param(
            '        run: uv run pytest backend/tests backend/app/tests rag/tests evaluation/tests evaluation/harness/tests evaluation/context_budget -m "not live"',
            "        run: |\n"
            "          uv run pytest backend/tests\n"
            '          uv run pytest backend/app/tests rag/tests evaluation/tests evaluation/harness/tests evaluation/context_budget -m "not live"',
            id="split-pytest-arguments",
        ),
        pytest.param(
            "run: uv run pytest backend/tests",
            "run: RESULT=$(uv run pytest backend/tests",
            id="command-substitution",
        ),
        pytest.param(
            "      - name: Run deterministic Python suites\n",
            "      - name: Run deterministic Python suites\n"
            "        continue-on-error: true\n",
            id="continue-on-error",
        ),
        pytest.param(
            "      - name: Run deterministic Python suites\n"
            '        run: uv run pytest backend/tests backend/app/tests rag/tests evaluation/tests evaluation/harness/tests evaluation/context_budget -m "not live"',
            "      - name: Run deterministic Python suites\n"
            "        shell: bash {0}\n"
            "        run: |\n"
            "          uv run pytest backend/tests backend/app/tests rag/tests evaluation/tests evaluation/harness/tests evaluation/context_budget "
            '-m "not live"\n\n'
            "          true",
            id="custom-shell-blank-line-multicommand",
        ),
    ],
)
def test_deterministic_gate_rejects_semantic_bypasses(
    tmp_path: Path, old: str, new: str
) -> None:
    """Known command, environment, and step-control bypasses must fail."""
    project_root = _mutated_project(tmp_path, old, new)

    assert DETERMINISTIC_GATE_FINDING in check_workflow_deploy(project_root)


@pytest.mark.parametrize(
    "operator", ["; true", "&& true", "|| true", "| cat", "& true"]
)
def test_deterministic_gate_rejects_shell_operators(
    tmp_path: Path, operator: str
) -> None:
    """Shell composition is outside the conservative deterministic-step contract."""
    project_root = _mutated_project(
        tmp_path,
        '-m "not live"',
        f'-m "not live" {operator}',
    )

    assert DETERMINISTIC_GATE_FINDING in check_workflow_deploy(project_root)


def test_deterministic_gate_accepts_safe_equals_marker_syntax(tmp_path: Path) -> None:
    """Quoted equals syntax remains one safe marker argument."""
    project_root = _mutated_project(
        tmp_path,
        '-m "not live"',
        "-m='not live'",
    )

    assert DETERMINISTIC_GATE_FINDING not in check_workflow_deploy(project_root)


def test_lambda_package_rejects_missing_deterministic_dependency(
    tmp_path: Path,
) -> None:
    """Packaging must not start unless the deterministic suite succeeds."""
    project_root = _mutated_project(
        tmp_path,
        "needs: [lint, test-deterministic]",
        "needs: lint",
    )

    assert LAMBDA_GATE_FINDING in check_workflow_deploy(project_root)


@pytest.mark.parametrize("condition", ["always()", "success()"])
def test_lambda_package_rejects_job_condition(tmp_path: Path, condition: str) -> None:
    """Packaging conservatively relies on the default successful-needs gate."""
    project_root = _mutated_project(
        tmp_path,
        "    needs: [lint, test-deterministic]",
        f"    needs: [lint, test-deterministic]\n    if: {condition}",
    )

    assert LAMBDA_GATE_FINDING in check_workflow_deploy(project_root)


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
    assert (
        "lambda PR preview workflows must fail closed without the dedicated preview deploy role"
        not in findings
    )


def test_lambda_preview_rejects_production_role_fallback(tmp_path: Path) -> None:
    """Preview jobs must never fall back to the production deployment role."""
    project_root = _mutated_project(
        tmp_path,
        "AWS_PREVIEW_DEPLOY_ROLE_ARN: ${{ secrets.AWS_PREVIEW_DEPLOY_ROLE_ARN }}",
        "AWS_PREVIEW_DEPLOY_ROLE_ARN: ${{ secrets.AWS_PREVIEW_DEPLOY_ROLE_ARN || secrets.AWS_DEPLOY_ROLE_ARN }}",
    )

    assert (
        "lambda PR preview workflows must fail closed without the dedicated preview deploy role"
        in check_workflow_deploy(project_root)
    )


def test_lambda_preview_cleanup_rejects_production_role_fallback(
    tmp_path: Path,
) -> None:
    """Cleanup must fail closed rather than assume the production role."""
    project_root = _mutated_checked_file(
        tmp_path,
        Path(".github/workflows/lambda-preview-cleanup.yml"),
        "AWS_PREVIEW_DEPLOY_ROLE_ARN: ${{ secrets.AWS_PREVIEW_DEPLOY_ROLE_ARN }}",
        "AWS_PREVIEW_DEPLOY_ROLE_ARN: ${{ secrets.AWS_PREVIEW_DEPLOY_ROLE_ARN || secrets.AWS_DEPLOY_ROLE_ARN }}",
    )

    assert (
        "lambda PR preview workflows must fail closed without the dedicated preview deploy role"
        in check_workflow_deploy(project_root)
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


def test_lambda_rollback_requires_completed_production_promotion_and_failed_smoke(
) -> None:
    """Pre-production failures must not trigger a production alias rollback."""
    findings = _findings()

    assert ROLLBACK_GUARD_FINDING not in findings


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            "needs.promote-lambda-production.result == 'success'",
            "failure()",
        ),
        (
            "needs.verify-lambda-production.result == 'failure'",
            "needs.verify-lambda-production.result == 'skipped'",
        ),
        (
            "needs.promote-lambda-production.outputs.previous-version != ''",
            "needs.promote-lambda-production.outputs.previous-version == ''",
        ),
        (
            "inputs.rollback_target_version != ''",
            "inputs.rollback_target_version == ''",
        ),
    ],
)
def test_lambda_rollback_rejects_broader_activation_conditions(
    tmp_path: Path, old: str, new: str
) -> None:
    """Rollback activation must remain bound to promotion, smoke, and target state."""
    project_root = _mutated_project(tmp_path, old, new)

    assert ROLLBACK_GUARD_FINDING in check_workflow_deploy(project_root)


def test_lambda_rollback_without_target_does_not_fail_the_workflow(
    tmp_path: Path,
) -> None:
    """A missing manual or unexpected rollback target must be a safe no-op."""
    project_root = _mutated_project(
        tmp_path,
        'echo "No rollback target version was discovered. Skipping rollback."\n'
        "            exit 0",
        'echo "No rollback target version was discovered. Skipping rollback."\n'
        "            exit 1",
    )

    assert ROLLBACK_TARGET_FINDING in check_workflow_deploy(project_root)
