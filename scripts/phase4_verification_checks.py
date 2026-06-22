"""Static checks for post-verification Lambda deployment cleanup.

These checks intentionally avoid live AWS, GitHub, Cloudflare, Docker, and
Terraform execution. They validate that local source-of-truth artifacts describe
the current Lambda/API Gateway/DynamoDB/custom-domain production path and that
retired EC2 Compose/Cloudflare Tunnel artifacts are no longer active.
"""

from pathlib import Path


GITIGNORE_PATH = Path(".gitignore")
ENV_EXAMPLE_PATH = Path(".env.example")
ADR_PATH = Path("docs/adr/009.md")
DEPLOYMENT_DOC_PATH = Path("docs/deployment.md")

ACTIVE_EC2_CHANGE_PATH = Path("openspec/changes/low-cost-ec2-compose-exposure")
ARCHIVED_EC2_CHANGE_PATH = Path(
    "openspec/changes/archive/2026-06-22-low-cost-ec2-compose-exposure"
)
FARGATE_SPEC_PATH = Path("openspec/specs/fargate-cloudflare-ingress/spec.md")
RUNTIME_SPEC_PATH = Path("openspec/specs/ecs-runtime-configuration/spec.md")
PROMOTION_SPEC_PATH = Path("openspec/specs/ecr-cd-promotion/spec.md")
STAGING_SPEC_PATH = Path("openspec/specs/local-staging-isolation/spec.md")


def check_phase4_verification_evidence(project_root: Path) -> list[str]:
    """Return source-coherence findings for Lambda-only production cleanup."""
    gitignore = _read(project_root / GITIGNORE_PATH)
    env_example = _read(project_root / ENV_EXAMPLE_PATH)
    adr = _read(project_root / ADR_PATH)
    deployment_doc = _read(project_root / DEPLOYMENT_DOC_PATH)
    fargate_spec = _read(project_root / FARGATE_SPEC_PATH)
    runtime_spec = _read(project_root / RUNTIME_SPEC_PATH)
    promotion_spec = _read(project_root / PROMOTION_SPEC_PATH)
    staging_spec = _read(project_root / STAGING_SPEC_PATH)

    findings: list[str] = []
    findings.extend(_check_env_deploy_ignored(gitignore))
    findings.extend(_check_env_example_lambda_semantics(env_example))
    findings.extend(_check_adr_custom_domain_semantics(adr))
    findings.extend(_check_deployment_doc_current_semantics(deployment_doc))
    findings.extend(
        _check_legacy_openspec_retired(
            project_root=project_root,
            fargate_spec=fargate_spec,
            runtime_spec=runtime_spec,
            promotion_spec=promotion_spec,
            staging_spec=staging_spec,
        )
    )
    return findings


def _check_env_deploy_ignored(gitignore: str) -> list[str]:
    ignored_entries = {
        line.strip()
        for line in gitignore.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if ".env.deploy" not in ignored_entries:
        return [".env.deploy must be ignored as local/manual deploy input"]
    return []


def _check_env_example_lambda_semantics(env_example: str) -> list[str]:
    required = [
        "Production Lambda resolves this from AWS SSM/Secrets",
        "OPENAI_API_KEY_SECRET_REF=",
        "CHAT_API_KEY_SECRET_REF=",
        "Production Lambda uses its execution role",
        "STATE_BACKEND=memory",
        "DYNAMODB_STATE_TABLE_NAME=",
        "LAMBDA_TIMEOUT_SECONDS=25",
        ".env.deploy, which must remain uncommitted",
    ]
    stale = ["in ECS", "ECS production", "task role, not static keys"]

    findings: list[str] = []
    if not _contains_all(env_example, required):
        findings.append(
            ".env.example must document Lambda secret refs, execution role, "
            "DynamoDB state, and local .env.deploy semantics"
        )
    if any(token in env_example for token in stale):
        findings.append(".env.example must not teach ECS production runtime semantics")
    return findings


def _check_adr_custom_domain_semantics(adr: str) -> list[str]:
    required = [
        "custom-domain DNS still uses a Cloudflare zone ID",
        "DNS management inputs, not Cloudflare Tunnel or Lambda runtime requirements",
        "does not restore Cloudflare Tunnel",
    ]
    stale = "Cloudflare account/zone" in adr

    if not _contains_all(adr, required) or stale:
        return [
            "ADR-009 must distinguish Cloudflare DNS custom-domain inputs from "
            "retired Cloudflare Tunnel requirements"
        ]
    return []


def _check_deployment_doc_current_semantics(deployment_doc: str) -> list[str]:
    stale_runtime_secret_evidence = [
        "currently needs rotation/update",
        "401 invalid_api_key",
    ]
    required = [
        "Lambda + API Gateway HTTP API",
        "Cloudflare zone/token only for DNS custom-domain management",
        "EC2 Compose/Cloudflare Tunnel production fallback has been removed",
    ]

    findings: list[str] = []
    if any(token in deployment_doc for token in stale_runtime_secret_evidence):
        findings.append(
            "deployment doc must not retain stale OpenAI 401 evidence after current deploy fix"
        )
    if not _contains_all(deployment_doc, required):
        findings.append(
            "deployment doc must keep Lambda/custom-domain deployment semantics explicit"
        )
    return findings


def _check_legacy_openspec_retired(
    *,
    project_root: Path,
    fargate_spec: str,
    runtime_spec: str,
    promotion_spec: str,
    staging_spec: str,
) -> list[str]:
    findings: list[str] = []

    if (project_root / ACTIVE_EC2_CHANGE_PATH).exists():
        findings.append("low-cost EC2 Compose OpenSpec change must be archived")
    if not (project_root / ARCHIVED_EC2_CHANGE_PATH / "archive-report.md").exists():
        findings.append("archived EC2 Compose change must include an archive report")

    if not _contains_all(
        fargate_spec,
        [
            "Retired Cloudflare Tunnel Ingress Specification",
            "Cloudflare Tunnel production ingress is retired",
            "DNS management does not restore Tunnel runtime",
        ],
    ):
        findings.append(
            "fargate-cloudflare-ingress spec must be retired or historical, "
            "not active production Tunnel guidance"
        )

    if "ECS task role" in runtime_spec or "ECS tasks receive" in runtime_spec:
        findings.append(
            "runtime configuration spec must not describe ECS task role as "
            "current backend production runtime"
        )
    if "production ECS" in promotion_spec or "ECS service update" in promotion_spec:
        findings.append(
            "promotion spec must not describe ECS as the current backend "
            "production deployment path"
        )
    if "production CI, Terraform state, Cloudflare tunnels" in staging_spec:
        findings.append(
            "local staging spec must include current serverless staging isolation semantics"
        )

    return findings


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)
