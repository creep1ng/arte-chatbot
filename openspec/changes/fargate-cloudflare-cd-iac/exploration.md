## Exploration: fargate-cloudflare-cd-iac

### Current State

The repository is container-ready but not deployment-ready:

- CI (`.github/workflows/ci.yml`) builds only the backend image with `docker compose build backend`, health-checks `/health`, runs the evaluation harness, uploads eval artifacts, and already uses GitHub OIDC for AWS credentials during evaluation S3 upload. It does not build/push frontend, push to ECR, register ECS task definitions, or deploy.
- Local runtime uses `docker-compose.yml` with `backend` on `8000` and `frontend` on `3000`; both read `.env`.
- Backend runtime still documents static AWS keys in `.env.example`, and `backend/app/s3_client.py` explicitly passes `aws_access_key_id` / `aws_secret_access_key` into `boto3.client(...)` when env/settings provide them. On ECS this should change to rely on the default credential provider chain from the ECS task role.
- `backend/main.py` currently hardcodes CORS to `http://localhost:3000`; production Cloudflare hostnames will require configurable allowed origins.
- The frontend is static HTML served by nginx (`frontend/Dockerfile`, `frontend/nginx.conf`) and generates `config.js` at container startup from `API_URL`, `LLM_MODEL`, and `GIT_COMMIT_HASH`.
- S3/File Inputs are core architecture: ADR-002 adopts S3 for datasheets, ADR-003 adopts File Inputs, ADR-004 defines `raw/` + `index/catalog_index.json`, and ADR-008 uploads evaluation history to S3.

Official-doc validation:

- Cloudflare Tunnel maps public hostnames to local services and supports `cloudflare/cloudflared:latest tunnel --no-autoupdate run --token <TUNNEL_TOKEN>` in Docker. It supports HTTP origins such as `http://localhost:8000` and multiple published applications per tunnel.
  - https://developers.cloudflare.com/tunnel/setup/
  - https://developers.cloudflare.com/tunnel/routing/
- ECS Fargate tasks using `awsvpc` networking let containers in the same task communicate over `localhost`.
  - https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-networking.html
- ECS Service Discovery/Cloud Map and Service Connect support ECS/Fargate service-to-service connectivity with DNS names/short names.
  - https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-discovery.html
  - https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-connect.html
- ECS has separate task execution role vs task role responsibilities: execution role pulls images, writes logs, and fetches task-definition secrets; task role grants application code access to AWS services such as S3.
  - https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html
  - https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html

### Affected Areas

- `.github/workflows/ci.yml` — add ECR push/promotion after CI + evaluation and prod deploy only for merges to `main`; keep staging out of CI.
- `backend/Dockerfile` / `frontend/Dockerfile` — keep image build inputs stable; frontend image already supports runtime config.
- `docker-compose.yml` — remains local dev; local-only staging scripts can build/run isolated stacks without sharing prod resources.
- `.env.example` — remove static AWS key requirement for deployed runtime; document task-role auth, AWS-native secrets/config, Cloudflare tunnel token, public URLs.
- `backend/app/s3_client.py` — stop forcing static credentials when absent; rely on boto3 default chain so ECS task role works cleanly.
- `backend/main.py` / `backend/app/config.py` — production CORS must use configured Cloudflare frontend/admin origins.
- `evaluation/harness/s3_upload.py` — CI already receives OIDC temporary credentials; avoid requiring static keys when `AWS_SESSION_TOKEN`/default AWS env credentials are present.
- New IaC/CD files — likely Terraform roots/modules for AWS ECS/Fargate/ECR/IAM/SSM/Secrets Manager and Cloudflare Tunnel/DNS/routes.

### Approaches

1. **Fargate sidecar per origin service** — Run `cloudflared` inside the same ECS task as each exposed origin.
   - Backend service task: `backend` + `cloudflared` sidecar; tunnel route `api.example.com -> http://localhost:8000`.
   - Frontend/admin service task: `frontend` + `cloudflared` sidecar; tunnel route `app.example.com/admin.example.com -> http://localhost:3000`.
   - Use separate tunnels per service/hostname group, or ensure every connector replica can reach every configured origin. A single shared tunnel across separate origin-specific tasks is risky because any replica may receive any hostname configured on that tunnel.
   - Pros: no ALB, direct evidence supports localhost in same Fargate task, smallest network surface, clean separation between prod services, simple security groups.
   - Cons: cloudflared lifecycle is coupled to each origin task; multiple tunnels/tokens to manage; scaling task count creates tunnel replicas and must be intentional.
   - Effort: Medium.

2. **Separate Fargate cloudflared edge service** — Run one or more `cloudflared` tasks as an ECS service and route to backend/frontend services using Cloud Map DNS or Service Connect.
   - Example routes: `api.example.com -> http://backend.production.internal:8000`, `app.example.com -> http://frontend.production.internal:3000`.
   - Backend/frontend services stay private and accept inbound only from the cloudflared service security group.
   - Pros: decouples ingress connector lifecycle from app tasks; one connector fleet can route multiple origins; better when admin UI and Chatwoot add more services.
   - Cons: more moving pieces; must configure service discovery/Service Connect correctly; adds an internal network dependency and health/debug surface.
   - Effort: Medium/High.

3. **EC2 fallback with cloudflared daemon/container** — Run app containers and `cloudflared` on ECS EC2 or plain EC2.
   - Pros: useful if host-level networking, persistent host daemon behavior, custom Docker networking, or cost-packing many tiny services becomes more important than managed runtime simplicity.
   - Cons: reintroduces server patching/capacity management; weaker fit for current containerized MVP; not required by the validated cloudflared/Fargate facts.
   - Effort: High operational overhead.

4. **Frontend on S3 + CloudFront later** — Keep frontend containerized behind Cloudflare Tunnel for v1, migrate static UI to S3+CloudFront when the UI stabilizes.
   - Pros v1 container: matches existing Dockerfile/runtime `config.js`, same deployment model as backend/admin, fewer new services during first infra cut.
   - Pros later S3+CloudFront: lower Fargate cost, no nginx task, better static asset delivery; AWS docs support static hosting with CloudFront for HTTPS/private-origin patterns.
   - Cons later migration: requires different CD path, cache invalidation/versioning, and deciding how runtime config is baked or generated.
   - Effort: Low for v1 container; Medium for later migration.

### Recommendation

Recommend Fargate as the primary platform. `cloudflared` is viable containerized on Fargate.

For v1, use **Fargate sidecar per exposed origin service** with separate tunnel scope per service/hostname group:

- `backend-prod` ECS service: backend container + cloudflared sidecar, public API hostname routed to `localhost:8000`.
- `frontend-prod` ECS service: frontend/admin container + cloudflared sidecar, public UI hostname routed to `localhost:3000`.
- Use ECS task execution role for ECR/logs/Secrets Manager or SSM injection; use ECS task role for application S3 access.
- Store sensitive runtime values (`OPENAI_API_KEY`, `CHAT_API_KEY`, Cloudflare tunnel token) in Secrets Manager or SSM SecureString; store non-sensitive config (`AWS_BUCKET_NAME`, `AWS_REGION`, public URLs, CORS origins, feature flags) in SSM Parameter Store or Terraform-managed environment values.
- CI should build backend + frontend images, run existing health/evaluation gates, push/promote images to ECR only after success, and deploy only on `main`. PRs can build/test but must not spawn AWS staging from CI.
- Local-only staging should use separate names, `.env.staging.local`, separate Cloudflare tunnel/token/hostnames, and isolated AWS parameters/bucket prefixes if needed; never reuse prod tunnel tokens or service names.

Use the **separate cloudflared edge service** if proposal/design prioritizes future extensibility over initial simplicity, especially once admin and Chatwoot need multiple private services behind one ingress layer. Keep EC2 only as fallback; no current evidence requires it.

### Risks

- A single remotely-managed Cloudflare tunnel shared across separate origin-specific ECS tasks can misroute if a connector replica receives traffic for a hostname whose local origin is absent. Use separate tunnels or a central connector that can reach all origins.
- Fargate tasks need outbound access to Cloudflare and AWS dependencies; private subnets require NAT or appropriate VPC endpoints plus internet egress for Cloudflare tunnel connections.
- ECS health must be defined in task definitions; Dockerfile `HEALTHCHECK` alone is not enough for ECS task health decisions.
- Current backend startup instantiates `FileInputsClient()` at module import, so deployed tasks require `OPENAI_API_KEY` available at startup.
- CORS is still hardcoded to localhost and will block production UI unless made configurable.
- Moving to IAM task roles requires code/config cleanup so boto3 does not depend on static AWS keys.
- PR image promotion semantics need a precise definition: PR builds should push immutable candidate tags only after gates pass, while prod deployment should consume a main/sha tag after merge.

### Ready for Proposal

Yes. Next phase should create a proposal that commits to Fargate-first IaC/CD, sidecar-per-origin for v1 unless the user explicitly prefers centralized ingress, AWS IAM task roles for S3, AWS-native secrets/config, ECR promotion after CI/evaluation, and local-only staging boundaries.
