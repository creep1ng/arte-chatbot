# Proposal: Low-Cost EC2 Compose Exposure

## Intent

Replace ECS/Fargate and per-service `cloudflared` sidecars with one low-cost EC2 Compose host and Cloudflare Tunnel. Keep HTTPS, avoid ALB/NAT costs, use latest Ubuntu LTS, and externalize backend flags plus service hostnames.

## Scope

### In Scope
- Compose host for backend, frontend, admin, `cloudflared`.
- One tunnel to Compose DNS origins.
- Hostnames supplied as external Terraform inputs.
- ECR promotion plus SSM deploys.
- Secrets via instance role and Secrets Manager/SSM.
- GitHub/Terraform backend env overrides.

### Out of Scope
- Local-staging migration.
- ALB/NLB, NAT, autoscaling, multi-AZ HA, blue/green.
- Application behavior changes.
- Moving secrets to GitHub Variables.
- Hardcoded AMI IDs or service hostnames.

## Capabilities

### New Capabilities
- `ec2-compose-cloudflare-exposure`: EC2 Compose tunnel exposure.

### Modified Capabilities
- `fargate-cloudflare-ingress`: Sidecars become central connector mode.
- `ecr-cd-promotion`: Deploys update EC2 Compose through SSM.
- `ecs-runtime-configuration`: Terraform-supplied backend env overrides.

## Approach

Add `ec2_compose_host`, dynamically select latest Ubuntu LTS, reuse ECR, and route one tunnel to Compose DNS origins. GitHub Actions passes `PROD_BACKEND_RUNTIME_ENV_JSON` plus hostname inputs from GitHub Secrets or equivalent into Terraform. Hostnames are hidden from source/IaC defaults, not cryptographically secret after Cloudflare publishes DNS. Secrets stay in Secrets Manager/SSM.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `infra/terraform/envs/prod/*` | Modified | Replace ECS; add AMI/env/host inputs. |
| `infra/terraform/modules/ec2_compose_host/*` | New | Host, IAM, security, Compose. |
| `infra/terraform/modules/cloudflare_tunnel/*` | Modified | Central connector and hostname inputs. |
| `.github/workflows/ci.yml` | Modified | SSM deploy with runtime/hostname inputs. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Single EC2 host outage | Med | Keep ECS rollback until verified. |
| Hostname disclosure | Low | Treat as source-hidden only; DNS becomes public. |
| Wrong tunnel origins | Med | Use Compose DNS; verify URLs. |

## Rollback Plan

Keep ECS/Fargate until EC2 health/routes pass. Repoint Cloudflare/DNS to prior tunnels and redeploy last ECS task definitions if needed.

## Dependencies

- AWS SSM, ECR, S3, Secrets Manager/SSM, Cloudflare Tunnel token.
- GitHub variable `PROD_BACKEND_RUNTIME_ENV_JSON` for non-sensitive config.
- GitHub Secrets or equivalent hostname inputs.

## Success Criteria

- [ ] One tunnel serves chatbot, app, and admin hostnames.
- [ ] Hostnames are external and absent from repo/IaC defaults.
- [ ] EC2 uses the latest Ubuntu LTS image without hardcoded AMI IDs.
- [ ] No public inbound app ports, ALB, or NAT Gateway.
- [ ] CI deploys ECR images to EC2 Compose via SSM.
- [ ] CI overrides non-sensitive backend flags via `PROD_BACKEND_RUNTIME_ENV_JSON`.
- [ ] Secrets remain in Secrets Manager/SSM.
- [ ] Backend health and UI URLs pass through Cloudflare after cutover.
