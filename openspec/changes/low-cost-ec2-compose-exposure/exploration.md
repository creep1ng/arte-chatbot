## Exploration: Low-Cost EC2 Compose Exposure

### Current State
Production currently uses ECS/Fargate for three independently deployed services: backend, frontend, and admin. `infra/terraform/envs/prod/main.tf` creates one ECS cluster, three `ecs_service` module instances, three Cloudflare Tunnel module instances, and three SSM-stored tunnel tokens. Each ECS task has a colocated `cloudflared` sidecar using `localhost` origins (`http://localhost:8000` for backend, `http://localhost:3000` for frontend/admin), which matches the existing `fargate-cloudflare-ingress` spec.

The current `ecs_service` module is Fargate-specific: it creates task/execution roles, CloudWatch logs, an outbound-only security group, an `aws_ecs_task_definition` with `requires_compatibilities = ["FARGATE"]`, and an `aws_ecs_service`. Production networking still depends on `private_subnet_ids` plus `assign_public_ip`; the variable descriptions note private subnets need NAT or VPC endpoints for outbound AWS/Cloudflare access. The deploy workflow currently applies Terraform on every production image deploy to update `backend_image_tag`, `frontend_image_tag`, and `admin_image_tag`.

`openspec/config.yaml` is not present, but OpenSpec directories and source specs already exist. For this exploration phase, only the minimal named-change artifact was created.

### Affected Areas
- `infra/terraform/envs/prod/main.tf` — replace production ECS services/per-service tunnels with one EC2 Compose host and one central Cloudflare Tunnel; keep ECR and URL locals.
- `infra/terraform/envs/prod/variables.tf` — replace Fargate/private-subnet inputs with public-subnet/EC2/tunnel/runtime inputs.
- `infra/terraform/envs/prod/outputs.tf` — replace ECS outputs with EC2 instance/deployment/public URL outputs.
- `infra/terraform/modules/cloudflare_tunnel/*` — already supports multiple hostnames only when `central_connector_mode = true`; production can reuse it for a single tunnel with Compose service DNS origins.
- `infra/terraform/modules/github_oidc/*` — deploy role currently grants ECS update/pass-role permissions; it would need SSM Run Command and EC2/SSM target discovery permissions instead.
- `.github/workflows/ci.yml` — production deploy job currently runs Terraform apply for image tags; it should shift app deploys to SSM Run Command after ECR promotion.
- `openspec/specs/fargate-cloudflare-ingress/spec.md` — existing requirements describe same-task sidecars; a new/changed spec should define central connector mode for EC2 Compose.
- `openspec/specs/ecr-cd-promotion/spec.md` — deployment requirements currently name ECS task definition/service updates and must evolve for EC2 Compose deployment.
- `openspec/specs/ecs-runtime-configuration/spec.md` — runtime credential requirements are ECS-specific and must be adapted to EC2 instance profile, host secret retrieval, and Compose env injection.

### Approaches
1. **Single EC2 host with Docker Compose and one central Cloudflare Tunnel** — Add an `ec2_compose_host` Terraform module, reuse ECR, create one Cloudflare tunnel with `central_connector_mode = true`, route hostnames to Compose service DNS names (`backend:8000`, `frontend:3000`, `admin:3000`), and deploy image tags through SSM Run Command.
   - Pros: lowest fixed cost, no ALB, no NAT Gateway, keeps Cloudflare HTTPS entrypoint, removes three always-on Fargate tasks and three tunnel connectors.
   - Cons: single point of failure, less managed than Fargate, host bootstrap/deploy/secrets handling becomes project-owned.
   - Effort: Medium

2. **Single ECS service running all app containers plus one cloudflared sidecar** — Keep ECS/Fargate but consolidate backend/frontend/admin/cloudflared into one task/service using one tunnel.
   - Pros: preserves ECS scheduling/log patterns and avoids EC2 host management.
   - Cons: still pays Fargate always-on cost, still requires outbound private networking strategy if private, couples all services into one task definition, does not fully satisfy lowest-cost target.
   - Effort: Medium

3. **Keep current per-service Fargate tunnels and optimize networking only** — Retain architecture and adjust public IP/VPC endpoints/NAT choices.
   - Pros: smallest architectural change and preserves existing specs closely.
   - Cons: does not remove triple compute/tunnel cost and likely misses the user's stated low-cost goal.
   - Effort: Low

### Recommendation
Proceed with Approach 1 for production only: one public-subnet EC2 instance with no public inbound app ports, Docker Compose for backend/frontend/admin/cloudflared, one Cloudflare Tunnel, ECR as image source, and SSM Session Manager/Run Command for access and deploys. This best matches the existing plan and cost target while preserving Cloudflare as the public ingress and avoiding ALB/NAT Gateway.

The proposal/spec phases should explicitly define a new production exposure capability rather than directly editing the existing Fargate-only behavior in place. Local staging should remain out of scope unless the user chooses to migrate it later.

### Risks
- EC2 host is a single point of failure; acceptable only if low fixed cost currently outranks HA.
- Secrets can leak into Terraform state or host disk if rendered carelessly; fetch runtime secrets at deploy/start time and keep files root-owned with restrictive permissions.
- Cloudflare origins must use Compose service DNS names, not `localhost`, because `cloudflared` will be a separate container.
- Replacing Terraform-per-deploy with SSM Run Command changes rollback and audit mechanics; deploy script must retain identifiable previous image tags.
- Existing specs are ECS/Fargate-specific; proposal/spec must carefully supersede production behavior without unintentionally breaking local-staging isolation.

### Ready for Proposal
Yes — create an OpenSpec proposal for `low-cost-ec2-compose-exposure` that scopes production migration to EC2 Compose, defines rollback to existing ECS/Fargate resources until cutover is verified, and defers local-staging migration.