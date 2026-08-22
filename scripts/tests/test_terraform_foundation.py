"""Validation tests for the PR2 Terraform foundation work unit."""

from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terraform_foundation_checks import check_foundation


ROOT = Path(__file__).resolve().parents[2]


def _findings() -> list[str]:
    return check_foundation(ROOT)


def _mutated_terraform_project(
    tmp_path: Path, relative_path: Path, old: str, new: str
) -> Path:
    """Copy static-check inputs and mutate one Terraform contract."""
    shutil.copytree(ROOT / "infra", tmp_path / "infra")
    shutil.copytree(ROOT / "admin", tmp_path / "admin")
    path = tmp_path / relative_path
    content = path.read_text(encoding="utf-8")
    assert old in content, f"mutation target is missing: {old}"
    path.write_text(content.replace(old, new, 1), encoding="utf-8")
    return tmp_path


def test_prod_is_lambda_only_without_ec2_or_cloudflare_tunnel_wiring() -> None:
    """Production must not require EC2, VPC/subnet, or Cloudflare Tunnel inputs."""
    findings = _findings()

    assert (
        "prod must be Lambda-only without EC2 or Cloudflare Tunnel wiring"
        not in findings
    )


def test_tunnel_tokens_and_secret_outputs_are_sensitive() -> None:
    """Cloudflare tunnel token material must not be exposed through plaintext outputs."""
    findings = _findings()

    assert "cloudflare tunnel token output must be sensitive" not in findings
    assert "secret value outputs must be sensitive" not in findings
    assert "prod outputs must not expose tunnel tokens" not in findings


def test_prod_hostnames_are_external_and_name_is_isolated_from_staging() -> None:
    """Prod root must use external sensitive hostnames without staging names."""
    findings = _findings()

    assert (
        "prod hostname variables must be sensitive inputs without defaults"
        not in findings
    )
    assert (
        "prod hostnames must not derive chatbot, app, and admin from domain_name"
        not in findings
    )
    assert "prod name prefix must reject staging values" not in findings


def test_admin_scaffold_is_a_separate_image() -> None:
    """Admin must be an independent container image/service, not a frontend route."""
    findings = _findings()

    assert "admin Dockerfile must exist" not in findings
    assert "admin nginx config must listen on port 3000" not in findings
    assert "admin image must copy admin source, not frontend source" not in findings


def test_lambda_backend_module_declares_serverless_runtime_foundation() -> None:
    """Lambda backend module must own compute, API, state, logs, IAM, and outputs."""
    findings = _findings()

    assert (
        "lambda_backend module must declare Lambda, alias, IAM, logs, DynamoDB, HTTP API, and invoke permission"
        not in findings
    )
    assert (
        "lambda_backend outputs must expose Lambda, alias, version, state table, and direct endpoint metadata"
        not in findings
    )


def test_lambda_backend_uses_role_credentials_without_vpc_or_static_keys() -> None:
    """Lambda module must use scoped IAM and avoid VPC/NAT/static credential wiring."""
    findings = _findings()

    assert (
        "lambda_backend module must not attach Lambda to a VPC or require NAT"
        not in findings
    )
    assert (
        "lambda_backend IAM policy must allow scoped S3, DynamoDB, SSM, and Secrets Manager access"
        not in findings
    )
    assert (
        "lambda_backend must not wire static AWS credentials or .env.deploy"
        not in findings
    )
    assert (
        "lambda_backend runtime_secret_arns must reject plaintext secret values"
        not in findings
    )
    assert (
        "lambda_backend must support a foundation-managed bounded execution role"
        not in findings
    )
    assert (
        "lambda_backend runtime must be python3.12 for package compatibility"
        not in findings
    )


def test_local_staging_wires_isolated_lambda_backend() -> None:
    """Local staging must add isolated serverless resources and direct endpoint output."""
    findings = _findings()

    assert (
        "local staging must wire an isolated lambda_backend module with staging alias, state prefix, and secret namespace"
        not in findings
    )
    assert "local staging must reject production S3 buckets by default" not in findings
    assert (
        "local staging secret ARNs must be staging/local-staging scoped" not in findings
    )
    assert (
        "local staging must tag resources with expiration cleanup metadata"
        not in findings
    )
    assert (
        "local staging outputs must expose the direct Lambda HTTP API endpoint"
        not in findings
    )


def test_pr_preview_wires_isolated_ephemeral_lambda_backend() -> None:
    """PR previews must use per-PR Lambda/API/DynamoDB resources and S3 state."""
    findings = _findings()

    assert (
        "PR preview must wire an isolated lambda_backend module with preview alias and state prefix"
        not in findings
    )
    assert "PR preview must tag resources for ownership and cleanup" not in findings
    assert (
        "PR preview variables must require PR identity, cleanup deadline, and non-production secrets"
        not in findings
    )
    assert (
        "PR preview outputs must expose endpoint and isolated state metadata"
        not in findings
    )
    assert (
        "PR preview Terraform state must use S3 backend configuration" not in findings
    )


def test_github_oidc_separates_production_and_preview_authority() -> None:
    """One provider must issue narrowly trusted, non-overlapping deploy roles."""
    findings = _findings()

    assert (
        "GitHub OIDC must use one provider with separate main and pull_request role subjects"
        not in findings
    )
    assert (
        "production deploy role must not create pull-request preview infrastructure"
        not in findings
    )
    assert (
        "preview deploy role must pass only the foundation runtime role and manage prefixed resources"
        not in findings
    )
    assert (
        "production foundation must expose reproducible preview role and boundary outputs"
        not in findings
    )


def test_preview_boundary_excludes_production_secret_namespaces() -> None:
    """The AWS permissions boundary, not PR Terraform, must enforce secret isolation."""
    findings = _findings()

    assert (
        "preview Lambda role must have a foundation-managed boundary limited to preview secrets"
        not in findings
    )


def test_oidc_check_rejects_preview_subject_widening(tmp_path: Path) -> None:
    """A broad repository subject must fail the OIDC trust contract."""
    project_root = _mutated_terraform_project(
        tmp_path,
        Path("infra/terraform/modules/github_oidc/main.tf"),
        "repo:${var.github_owner}/${var.github_repository}:pull_request",
        "repo:${var.github_owner}/${var.github_repository}:*",
    )

    assert (
        "GitHub OIDC must use one provider with separate main and pull_request role subjects"
        in check_foundation(project_root)
    )


def test_boundary_check_rejects_production_secret_namespace(
    tmp_path: Path,
) -> None:
    """A production namespace accidentally admitted by the boundary must fail."""
    project_root = _mutated_terraform_project(
        tmp_path,
        Path("infra/terraform/modules/github_oidc/main.tf"),
        "parameter/arte-chatbot/pr-preview/*",
        "parameter/arte-chatbot/prod/*",
    )

    assert (
        "preview Lambda role must have a foundation-managed boundary limited to preview secrets"
        in check_foundation(project_root)
    )
