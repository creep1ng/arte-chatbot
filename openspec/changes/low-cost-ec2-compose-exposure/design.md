# Design: Low-Cost EC2 Compose Exposure

## Technical Approach

Production keeps ECR and Cloudflare-managed HTTPS, but replaces ECS/Fargate and same-task `cloudflared` sidecars with one public-subnet Ubuntu LTS EC2 Docker Compose host. Terraform owns infrastructure and `/opt/arte-chatbot`; GitHub Actions builds SHA-tagged ECR images, passes non-sensitive backend overrides through `TF_VAR_backend_runtime_environment_variables` from `PROD_BACKEND_RUNTIME_ENV_JSON || '{}'`, and deploys through SSM Run Command. Secrets stay in `PROD_BACKEND_RUNTIME_SECRET_ARNS_JSON` and Secrets Manager/SSM.

The normal AMI path is Terraform resolution, not a committed AMI id: `infra/terraform/envs/prod/main.tf` uses an AWS provider `aws_ami` data source with Canonical owner `099720109477`, HVM/EBS filters, and an Ubuntu LTS server image filter, with `most_recent = true`. An optional `ami_id_override` may exist only for emergency pinning.

Service public hostnames are external Terraform inputs sourced from GitHub Secrets or equivalent secure CI inputs, marked `sensitive`, and have no repo defaults. Terraform may still create Cloudflare DNS records, so hostname secrecy only prevents source/default exposure; DNS names become public after creation.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Runtime platform | One Ubuntu LTS EC2 instance with Docker Compose | Keep Fargate; one Fargate task | Meets low fixed-cost goal and removes ALB/NAT, accepting single-host risk. |
| AMI selection | `data.aws_ami.ubuntu_lts` using Canonical owner/filter; optional `ami_id_override` only | Required `ami_id`; Amazon Linux SSM parameter | Avoids stale hardcoded AMIs while matching the accepted Ubuntu LTS decision. |
| Hostname inputs | Sensitive Terraform variables such as `backend_hostname`, `frontend_hostname`, `admin_hostname`, supplied by GitHub Secrets/equivalent | Hardcoded `chatbot/app/admin` labels or defaults | Keeps service names out of source/IaC defaults; DNS publication remains public by nature. |
| Tunnel topology | One `edge_tunnel` in central mode with origins `http://backend:8000`, `http://frontend:3000`, `http://admin:3000` | Per-service tunnels; `localhost` origins | `cloudflared` is a separate Compose service, so Compose DNS is required. |
| Deploy flow | Workflow invokes `/opt/arte-chatbot/deploy.sh sha-${{ github.sha }}` through SSM | Terraform apply on every app deploy | Separates infra from release and retains immutable ECR tags. |

## Data Flow

```text
GitHub Secrets hostnames -> TF_VAR_*_hostname -> Terraform Cloudflare routes/DNS
data.aws_ami.ubuntu_lts -> EC2 Compose host -> Docker Compose services
Browser/WhatsApp -> Cloudflare DNS/Proxy -> single Tunnel
  -> cloudflared Compose service -> backend/frontend/admin Compose DNS origins
deploy -> GitHub OIDC -> ECR push -> SSM Run Command -> deploy.sh -> compose up -d
Secrets Manager/SSM ARNs -> runtime secret fetch -> secret env file -> Compose env
```

The EC2 security group allows outbound HTTPS/Cloudflare tunnel egress and no public app ports. Admin access uses SSM Session Manager.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `infra/terraform/modules/ec2_compose_host/main.tf` | Create | EC2, security group, instance profile, SSM/ECR/S3/secrets IAM, bootstrap templates. |
| `infra/terraform/modules/ec2_compose_host/variables.tf` | Create | VPC/subnet, optional AMI override, instance size, images, URLs, secret refs, bucket, tunnel token secret. |
| `infra/terraform/modules/ec2_compose_host/templates/docker-compose.yml.tftpl` | Create | Compose stack for `backend`, `frontend`, `admin`, and `cloudflared`. |
| `infra/terraform/modules/ec2_compose_host/templates/deploy.sh.tftpl` | Create | ECR login, tag file, image pull, stack restart, previous tag for rollback. |
| `infra/terraform/envs/prod/main.tf` | Modify | Add Canonical Ubuntu LTS `aws_ami` data source, remove hardcoded hostname labels, create one central tunnel, and pass EC2 host config. |
| `infra/terraform/envs/prod/variables.tf` | Modify | Replace Fargate inputs; add sensitive hostname variables, optional `ami_id_override`, and `backend_runtime_environment_variables` default `{}`. |
| `infra/terraform/envs/prod/outputs.tf` | Modify | Replace ECS outputs with EC2 host/deploy outputs while keeping public/ECR URLs sensitive where derived from hostname inputs. |
| `infra/terraform/modules/cloudflare_tunnel/*` | Modify | Reuse multi-host validation; update wording from ECS sidecar to generic connector. |
| `infra/terraform/modules/github_oidc/*` | Modify | Replace ECS/pass-role permissions with scoped SSM Run Command permissions. |
| `.github/workflows/ci.yml` | Modify | Source hostname TF vars from GitHub Secrets/equivalent, pass runtime JSON, then call SSM deploy. |

## Interfaces / Contracts

Compose names are the tunnel contract: `backend:8000`, `frontend:3000`, `admin:3000`. Hostname variables are required, sensitive strings without defaults; Terraform derives public URLs/CORS from them. `/opt/arte-chatbot/deploy.sh <sha-tag>` fails on bad ECR pull, Compose restart, or health check. Runtime env preserves backend defaults and allows non-sensitive string overrides; secrets MUST stay in `backend_runtime_secret_arns` / `PROD_BACKEND_RUNTIME_SECRET_ARNS_JSON`.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Static | Terraform syntax/module wiring | `terraform -chdir=infra/terraform/envs/prod fmt -recursive` and `terraform validate`. |
| Static | AMI and hostname policy | Plan shows Canonical Ubuntu LTS data source/override behavior; no repo default `chatbot/app/admin` hostname labels. |
| Unit/static | No plaintext secrets, Compose DNS origins, env override merge | Review/render plan; secret ARNs remain references and hostname inputs are sensitive. |
| Integration | EC2 joins SSM, pulls ECR, reads S3, starts Compose | Apply in maintenance window, run SSM command, inspect `docker compose ps` and logs. |
| E2E | Public URLs through Cloudflare | `curl -f https://$BACKEND_HOSTNAME/health`, `https://$FRONTEND_HOSTNAME/`, `https://$ADMIN_HOSTNAME/`. |

## Migration / Rollout

First configure GitHub Secrets/equivalent for required hostnames, tunnel secret, and secret ARN JSON. Apply EC2/tunnel infrastructure while keeping ECS rollback available. Deploy the current SHA; verify selected Ubuntu AMI, SSM, health, effective backend env, routes, and URLs. Cut over to the single tunnel. Rollback restores the last Fargate commit/state path, prior routing, and ECS task definitions. After verification, remove obsolete ECS/Fargate resources and old tunnel secrets.

## Open Questions

None.
