# Retired Cloudflare Tunnel Ingress Specification

## Purpose

Record that the ECS/Fargate + Cloudflare Tunnel production ingress model is no
longer an active backend deployment requirement. The current backend production
boundary is API Gateway HTTP API -> Lambda, with Cloudflare used only for DNS
custom-domain management when enabled.

## Requirements

### Requirement: Cloudflare Tunnel production ingress is retired

The production backend MUST NOT require ECS/Fargate services, same-task
`cloudflared` sidecars, Cloudflare Tunnel tokens, or tunnel routes. Historical
Tunnel requirements MUST remain in archived OpenSpec changes only.

#### Scenario: Lambda custom domain replaces tunnel ingress

- GIVEN production backend ingress is validated
- WHEN the public backend hostname is configured
- THEN traffic routes through API Gateway HTTP API and Lambda
- AND Cloudflare Tunnel is not required for backend production traffic

#### Scenario: DNS management does not restore Tunnel runtime

- GIVEN Terraform manages the backend custom domain in Cloudflare DNS
- WHEN ACM validation and backend CNAME records are created
- THEN the Cloudflare zone ID and provider token are used only for DNS changes
- AND no Cloudflare Tunnel token or connector sidecar is required

#### Scenario: Historical Tunnel artifacts stay archived

- GIVEN an operator needs the previous Fargate or EC2 Tunnel design rationale
- WHEN they inspect OpenSpec history
- THEN the superseded change artifacts are available under
  `openspec/changes/archive/`
- AND active specs do not present that path as current production architecture
