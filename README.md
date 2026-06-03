# ARTE Chatbot

ARTE Chatbot is a FastAPI-based customer support chatbot for Arte Soluciones Energéticas. It uses OpenAI file inputs over product datasheets stored in S3, plus evaluation tooling for quality and escalation checks.

## Quick start

```bash
cp .env.example .env
# fill OPENAI_API_KEY and CHAT_API_KEY
docker compose up -d
curl http://localhost:8000/health
```

## Project structure

| Path | Purpose |
|------|---------|
| `backend/` | FastAPI API, sessions, auth, S3 access, and LLM orchestration. |
| `frontend/` | Public static UI container. |
| `admin/` | Separate admin static UI container. |
| `rag/` | File-input retrieval orchestration. |
| `evaluation/` | Evaluation harnesses and datasets. |
| `infra/terraform/` | ECR, ECS Fargate, Cloudflare Tunnel, IAM/OIDC, SSM/Secrets IaC. |
| `scripts/` | Validation and local staging helper scripts. |
| `docs/` | ADRs and deployment guides. |

## Runtime configuration

Local development uses `.env`. Production ECS runtime uses AWS Secrets Manager or SSM for secrets and IAM roles/default credential chains for AWS access.

| Variable | Local | Production |
|----------|-------|------------|
| `OPENAI_API_KEY` | `.env` | Secrets Manager/SSM ECS secret ref |
| `CHAT_API_KEY` | `.env` | Secrets Manager/SSM ECS secret ref |
| `AWS_BUCKET_NAME` | `.env` | Terraform task environment |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Optional local credential-chain source | Not required; use ECS task role |
| `DOMAIN_NAME` | Optional, defaults to `artesolutions.com.co` | `artesolutions.com.co` |
| `ALLOWED_CORS_ORIGINS` | Localhost origins | Explicit Cloudflare origins; no wildcard in production |

## Data infrastructure

Product datasheets live in Amazon S3:

```text
arte-chatbot-data/
├── raw/
│   ├── paneles/
│   ├── inversores/
│   ├── controladores/
│   └── baterias/
└── index/
    └── catalog_index.json
```

The backend reads `index/catalog_index.json`, selects a product PDF, and sends the file to the LLM as a File Input. See ADR-002 and ADR-003 for the architecture decisions.

## CI/CD and deployment

GitHub Actions builds backend, frontend, and admin images. Tests, health checks, and evaluation must pass before ECR images are pushed.

| Flow | Behavior |
|------|----------|
| Pull request | Builds/evaluates and may push immutable candidate tags: `pr-<number>-sha-<commit>` and `sha-<commit>`. No production deploy. |
| `main` push | Pushes `sha-<commit>` tags, assumes AWS through OIDC, and applies production Terraform. |
| Local staging | Developer-run only through `scripts/deploy-local-staging.sh`; never created by CI. |

Deployment details: [docs/deployment.md](docs/deployment.md).

## Local development

### Docker Compose

```bash
cp .env.example .env
docker compose up -d
curl http://localhost:8000/health
docker compose logs -f backend
docker compose down
```

### Python without Docker

```bash
uv venv
uv sync --group dev --group lint --group typecheck
uv run uvicorn backend.main:app --reload
```

## Testing

```bash
uv run pytest
uv run pytest backend/tests/test_config.py
uv run ruff check backend/ evaluation/ scripts/
```

Focused deployment guard checks:

```bash
uv run pytest scripts/tests/test_cd_and_staging_guards.py
```

## Local staging

Use an immutable candidate ECR tag produced by PR CI, or an explicit `local-*` tag you pushed yourself:

```bash
scripts/deploy-local-staging.sh \
  --staging-id pr-123 \
  --backend-tag pr-123-sha-abcdef1 \
  --frontend-tag pr-123-sha-abcdef1 \
  --admin-tag pr-123-sha-abcdef1 \
  --plan-only
```

The script rejects CI execution, production-like names, implicit tags, and expirations beyond three days. Destroy staging when finished with `--destroy`.

## Catalog indexing

```bash
python scripts/generate_index.py --dry-run
python scripts/generate_index.py --bucket arte-chatbot-data --prefix raw/ --output docs/data/catalog_index.example.json
```

## Security rules

- Never commit `.env`, Cloudflare tokens, AWS keys, OpenAI keys, or chat API keys.
- Use IAM roles/OIDC/default credential chains for deployed AWS access.
- Keep local staging secrets, state, parameter paths, and hostnames isolated from production.
