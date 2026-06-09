"""Static guard checks for PR3 CD and local-staging deployment safety.

The checks intentionally read workflow, script, and Terraform files only. They do
not call AWS, Cloudflare, Docker, or Terraform, so they are safe for PR CI.
"""

from pathlib import Path
import re


WORKFLOW_PATH = Path(".github/workflows/ci.yml")
ADMIN_WORKFLOW_PATH = Path(".github/workflows/admin-panel.yml")
COMPOSE_PATH = Path("docker-compose.yml")
PROD_ROOT = Path("infra/terraform/envs/prod")
LOCAL_STAGING_ROOT = Path("infra/terraform/envs/local-staging")
DEPLOY_SCRIPT_PATH = Path("scripts/deploy-local-staging.sh")


DEPLOYABLE_SERVICES = ("backend", "admin")


def check_cd_and_staging_guards(project_root: Path) -> list[str]:
    """Return static CD/local-staging guard findings for the project."""
    findings: list[str] = []

    workflow = _read(project_root / WORKFLOW_PATH)
    admin_workflow = _read(project_root / ADMIN_WORKFLOW_PATH)
    compose = _read(project_root / COMPOSE_PATH)
    prod_main = _read(project_root / PROD_ROOT / "main.tf")
    prod_variables = _read(project_root / PROD_ROOT / "variables.tf")
    prod_outputs = _read(project_root / PROD_ROOT / "outputs.tf")
    staging_main = _read(project_root / LOCAL_STAGING_ROOT / "main.tf")
    staging_variables = _read(project_root / LOCAL_STAGING_ROOT / "variables.tf")
    staging_outputs = _read(project_root / LOCAL_STAGING_ROOT / "outputs.tf")
    staging_providers = _read(project_root / LOCAL_STAGING_ROOT / "providers.tf")
    deploy_script = _read(project_root / DEPLOY_SCRIPT_PATH)

    findings.extend(_check_workflow(workflow))
    findings.extend(_check_admin_workflow(admin_workflow))
    findings.extend(_check_compose(compose))
    findings.extend(_check_production_root(prod_main, prod_variables, prod_outputs))
    findings.extend(
        _check_local_staging_root(
            staging_main,
            staging_variables,
            staging_providers,
            staging_outputs,
        )
    )
    findings.extend(_check_deploy_script(deploy_script))

    return findings


def _check_workflow(workflow: str) -> list[str]:
    findings: list[str] = []

    build_mentions = [f"{service}_image" in workflow or f"{service}-image" in workflow for service in DEPLOYABLE_SERVICES]
    dockerfiles = [f"{service}/Dockerfile" in workflow or f"{service}-panel/Dockerfile" in workflow for service in DEPLOYABLE_SERVICES]
    if not all(build_mentions) or not all(dockerfiles):
        findings.append("workflow must build backend and admin-panel images")

    if _contains_any(workflow, ["frontend-image", "frontend/Dockerfile", "arte-chatbot-frontend", "FRONTEND_ECR_REPOSITORY_URL"]):
        findings.append("workflow must not build or promote standalone frontend images")

    publish_job = _job_block(workflow, "publish-candidate-images")
    if not publish_job or not _contains_all(publish_job, ["needs: evaluation", "docker push"]):
        findings.append("candidate image push must wait for test-health and evaluation gates")

    if not _contains_all(workflow, ["pr-${{ github.event.pull_request.number }}-sha-${{ github.sha }}", "sha-${{ github.sha }}"]):
        findings.append("candidate tags must include PR and SHA rollback identifiers")

    deploy_job = _job_block(workflow, "deploy-production")
    if not deploy_job or "github.event_name == 'push' && github.ref == 'refs/heads/main'" not in deploy_job:
        findings.append("production deploy job must be gated to push events on refs/heads/main")

    if not deploy_job or not _contains_all(
        deploy_job,
        ["permissions:", "id-token: write", "aws-actions/configure-aws-credentials@v4", "role-to-assume"],
    ):
        findings.append("production deploy job must configure AWS credentials through OIDC")
    if not deploy_job or not _contains_all(
        deploy_job,
        ["CLOUDFLARE_API_TOKEN", "TF_VAR_vpc_id", "TF_VAR_private_subnet_ids", "TF_VAR_backend_runtime_secret_arns"],
    ):
        findings.append("production deploy job must provide Terraform AWS and Cloudflare inputs")

    pr_guard = "github.event_name == 'pull_request'" in publish_job if publish_job else False
    if not pr_guard or (deploy_job and "pull_request" in deploy_job):
        findings.append("pull requests must not contain a production deploy job path")

    return findings


def _check_admin_workflow(admin_workflow: str) -> list[str]:
    findings: list[str] = []

    if not _contains_all(admin_workflow, ["admin-panel/**", "npm run lint", "npm run typecheck", "npm run test:unit"]):
        findings.append("admin-panel workflow must keep lint, typecheck, and unit tests deployable")
    if "frontend/**" in admin_workflow:
        findings.append("admin-panel workflow must not trigger on standalone frontend changes")

    return findings


def _check_compose(compose: str) -> list[str]:
    findings: list[str] = []

    if not _contains_all(compose, ["backend:", "admin-panel:", '"8000:8000"', '"3001:3000"']):
        findings.append("compose must expose only backend and admin-panel browser services")
    if _contains_any(compose, ["frontend:", "frontend/Dockerfile", '"3000:3000"', "arte-chatbot-frontend"]):
        findings.append("compose must not expose standalone frontend as a browser access path")

    return findings


def _check_production_root(main_tf: str, variables_tf: str, outputs_tf: str) -> list[str]:
    findings: list[str] = []

    if not main_tf or not variables_tf or not outputs_tf:
        return ["production Terraform root must exist"]

    if not _contains_all(main_tf, ["module \"backend_service\"", "module \"admin_service\"", "local.public_admin_url"]):
        findings.append("production Terraform must keep backend and admin services deployable")
    if _contains_any(
        "\n".join([main_tf, variables_tf, outputs_tf]),
        [
            "frontend_service",
            "frontend_cloudflare_tunnel",
            "frontend_ecr",
            "frontend_image_tag",
            "frontend_tunnel_secret",
            "PUBLIC_FRONTEND_URL",
            "public_frontend_url",
            "local.frontend_hostname",
            "frontend =",
        ],
    ):
        findings.append("production Terraform must not configure standalone frontend runtime")

    return findings


def _check_local_staging_root(main_tf: str, variables_tf: str, providers_tf: str, outputs_tf: str) -> list[str]:
    findings: list[str] = []

    if not main_tf or not variables_tf or not providers_tf:
        return ["local-staging Terraform root must exist"]

    if 'backend "local"' not in providers_tf:
        findings.append("local-staging must use isolated local backend state")

    if not _contains_all(
        main_tf,
        [
            'environment = "local-staging"',
            "staging-chatbot-api-${var.staging_id}",
            "staging-chatbot-admin-${var.staging_id}",
        ],
    ):
        findings.append("local-staging must derive unique staging hostnames from staging_id")

    if not _contains_all(variables_tf, ["api", "app", "admin", "prod", "production", "artesolutions.com.co"]):
        findings.append("local-staging must reject production hostnames and names")

    if not _contains_all(main_tf, ["/local-staging/", "backend_runtime_secret_arns", "cloudflare_tunnel_secrets"]):
        findings.append("local-staging must isolate secret and parameter namespaces")

    if "timeadd(timestamp(), \"72h\")" not in main_tf and "expiration_at" not in variables_tf:
        findings.append("local-staging must record expiration metadata")

    if not _contains_all(main_tf, ["module \"backend_service\"", "module \"admin_service\"", "local.public_admin_url"]):
        findings.append("local-staging must keep backend and admin services deployable")
    if _contains_any(
        "\n".join([main_tf, variables_tf, outputs_tf]),
        [
            "frontend_service",
            "frontend_cloudflare_tunnel",
            "frontend_image_tag",
            "frontend_tunnel_secret",
            "frontend_ecr_repository",
            "PUBLIC_FRONTEND_URL",
            "public_frontend_url",
            "local.frontend_hostname",
            "frontend =",
        ],
    ):
        findings.append("local-staging Terraform must not configure standalone frontend runtime")

    return findings


def _check_deploy_script(script: str) -> list[str]:
    findings: list[str] = []

    if not _contains_all(script, ["CI", "GITHUB_ACTIONS", "local staging cannot run in CI"]):
        findings.append("deploy script must reject CI execution")
    if not _contains_all(script, ["--backend-tag", "--admin-tag", "explicit immutable ECR tag"]):
        findings.append("deploy script must require explicit image tags")
    if _contains_any(script, ["--frontend-tag", "FRONTEND_TAG", "TF_VAR_frontend"]):
        findings.append("deploy script must not require standalone frontend tags")
    if not _contains_all(script, ["staging-chatbot", "api|app|admin", "expiration must be no later than 3 days"]):
        findings.append("deploy script must reject prod names and long expirations")
    if not _contains_all(script, ["TF_VAR_vpc_id", "TF_VAR_private_subnet_ids", "CLOUDFLARE_API_TOKEN"]):
        findings.append("deploy script must require local-only Terraform and Cloudflare inputs")

    return findings


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


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)
