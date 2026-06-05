"""Static checks for the production EC2 Compose deploy workflow.

The checks read repository files only. They intentionally avoid GitHub, AWS,
Cloudflare, Docker, and Terraform calls so they can run safely in PR CI.
"""

from pathlib import Path
import re


WORKFLOW_PATH = Path(".github/workflows/ci.yml")
SERVICES = ("backend", "frontend", "admin")


def check_workflow_deploy(project_root: Path) -> list[str]:
    """Return static findings for the production deploy workflow contract."""
    workflow = _read(project_root / WORKFLOW_PATH)
    deploy_job = _job_block(workflow, "deploy-production")
    publish_release_job = _job_block(workflow, "publish-release-images")
    publish_candidate_job = _job_block(workflow, "publish-candidate-images")

    findings: list[str] = []
    findings.extend(_check_main_deploy_gates(deploy_job, publish_release_job, publish_candidate_job))
    findings.extend(_check_external_inputs(deploy_job))
    findings.extend(_check_ssm_deploy(deploy_job, publish_release_job))
    findings.extend(_check_cloudflare_health(deploy_job))
    return findings


def _check_main_deploy_gates(
    deploy_job: str,
    publish_release_job: str,
    publish_candidate_job: str,
) -> list[str]:
    findings: list[str] = []

    if not deploy_job or "github.event_name == 'push' && github.ref == 'refs/heads/main'" not in deploy_job:
        findings.append("production deploy job must run only on push events to refs/heads/main")

    if not deploy_job or "needs: publish-release-images" not in deploy_job:
        findings.append("production deploy job must depend on release image promotion after evaluation gates")
    if not publish_release_job or "needs: evaluation" not in publish_release_job:
        findings.append("production deploy job must depend on release image promotion after evaluation gates")

    pr_candidate_guard = "github.event_name == 'pull_request'" in publish_candidate_job
    deploy_mentions_pr = "pull_request" in deploy_job if deploy_job else True
    if not pr_candidate_guard or deploy_mentions_pr:
        findings.append("pull requests must not have any production deploy path")

    return findings


def _check_external_inputs(deploy_job: str) -> list[str]:
    findings: list[str] = []

    hostname_secret_inputs = [
        f"TF_VAR_{service}_hostname: ${{{{ secrets.PROD_{service.upper()}_HOSTNAME }}}}"
        for service in SERVICES
    ]
    if not deploy_job or not _contains_all(deploy_job, hostname_secret_inputs):
        findings.append("production deploy must pass backend/frontend/admin hostnames from secrets")

    forbidden_hostname_literals = (
        "artesolutions.com.co",
        "chatbot.",
        "api.",
        "app.",
    )
    if deploy_job and any(literal in deploy_job for literal in forbidden_hostname_literals):
        findings.append("production deploy must not hardcode service hostnames in workflow source")

    runtime_env = "TF_VAR_backend_runtime_environment_variables: ${{ vars.PROD_BACKEND_RUNTIME_ENV_JSON || '{}' }}"
    if not deploy_job or runtime_env not in deploy_job:
        findings.append("production deploy must pass backend runtime env from vars with {} fallback")

    if not deploy_job or "TF_VAR_backend_runtime_secret_arns: ${{ secrets.PROD_BACKEND_RUNTIME_SECRET_ARNS_JSON }}" not in deploy_job:
        findings.append("production deploy must keep backend secrets in runtime secret ARNs")

    return findings


def _check_ssm_deploy(deploy_job: str, publish_release_job: str) -> list[str]:
    findings: list[str] = []

    required_release_tags = [
        f"push_if_missing arte-chatbot-{service} \"${{{{ vars.{service.upper()}_ECR_REPOSITORY_URL }}}}\" \"${{SHA_TAG}}\""
        for service in SERVICES
    ]
    if not publish_release_job or not _contains_all(publish_release_job, required_release_tags):
        findings.append("production deploy must keep SHA-tagged ECR release images")

    ssm_needles = [
        "aws ssm send-command",
        "AWS-RunShellScript",
        "/opt/arte-chatbot/deploy.sh ${SHA_TAG}",
        "aws ssm wait command-executed",
        "terraform -chdir=infra/terraform/envs/prod output -json ec2_compose_host",
    ]
    if not deploy_job or not _contains_all(deploy_job, ssm_needles):
        findings.append("production deploy must invoke /opt/arte-chatbot/deploy.sh through SSM")

    forbidden_ecs_paths = ("Deploy Production ECS Services", "aws ecs", "ecs update-service", "force-new-deployment")
    if deploy_job and any(path in deploy_job for path in forbidden_ecs_paths):
        findings.append("production deploy must not keep ECS service update paths")

    return findings


def _check_cloudflare_health(deploy_job: str) -> list[str]:
    if not deploy_job or not _contains_all(
        deploy_job,
        ["https://${TF_VAR_backend_hostname}/health", "curl", "TF_VAR_backend_hostname"],
    ):
        return ["production deploy must verify backend health through the Cloudflare hostname"]
    return []


def _job_block(workflow: str, job_name: str) -> str:
    pattern = re.compile(rf"^  {re.escape(job_name)}:\n(?P<body>(?:    .+\n|\n)+)", re.MULTILINE)
    match = pattern.search(workflow)
    return match.group(0) if match else ""


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)
