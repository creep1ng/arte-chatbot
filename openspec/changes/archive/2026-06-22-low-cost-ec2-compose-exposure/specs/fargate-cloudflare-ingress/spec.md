# Delta for Fargate Cloudflare Ingress

## MODIFIED Requirements

### Requirement: Same-task Cloudflare Tunnel Sidecars

Production MUST NOT deploy public origins as per-service ECS/Fargate tasks with same-task `cloudflared` sidecars. Non-production Fargate origins MAY continue using same-task sidecars where explicitly retained.
(Previously: every public Fargate origin required a same-task sidecar and `localhost` route.)

#### Scenario: Production no longer uses localhost sidecar

- GIVEN production ingress is configured
- WHEN Terraform applies the production exposure configuration
- THEN production hostnames are not routed to per-service `http://localhost` Fargate sidecars
- AND production can serve traffic without an ALB

#### Scenario: Retained non-production sidecar

- GIVEN a deferred non-production environment still uses Fargate sidecars
- WHEN its UI or API ingress is applied
- THEN its connector MAY continue routing to its same-task localhost origin

### Requirement: Scoped Tunnel Ownership

The system MUST use a separate tunnel per service unless central-connector mode is explicitly configured and every connector can reach every origin.
(Previously: separate backend/frontend tunnels were required unless central reachability was explicit.)

#### Scenario: Production central tunnel allowed

- GIVEN production backend, frontend, and admin origins are reachable on one Compose network
- WHEN one production tunnel is configured in central-connector mode
- THEN all production hostnames MAY attach to that tunnel
- AND each route targets a reachable Compose service origin

#### Scenario: Shared tunnel rejected when origins are unreachable

- GIVEN one tunnel has backend and frontend hostnames
- AND a connector replica can reach only one origin
- WHEN Terraform validates or plans the ingress configuration
- THEN the configuration MUST fail or require explicit central-connector mode

### Requirement: Terraform-managed Cloudflare Routes

Terraform MUST manage Cloudflare tunnel resources, hostname routes, and DNS records for deployed services, while keeping tunnel tokens out of plaintext outputs. Production service hostnames MUST be provided through external sensitive inputs or GitHub Secrets/equivalent rather than hardcoded source defaults; created DNS records MAY be public.
(Previously: Terraform managed per-service tunnel routes and tokens without requiring externalized production hostnames.)

#### Scenario: Public hostname provisioned

- GIVEN production declares API, app, and admin public hostnames
- WHEN Terraform is applied
- THEN the corresponding Cloudflare routes and DNS records are created or updated on one tunnel
- AND the tunnel token is referenced through a secret source

#### Scenario: Token not exposed

- GIVEN Terraform stores or passes a tunnel token to the runtime
- WHEN Terraform outputs are inspected
- THEN the raw token value MUST NOT appear in non-sensitive outputs

#### Scenario: Production hostnames not hardcoded

- GIVEN production API, app, and admin hostname values are provided by deploy-time inputs
- WHEN Terraform applies Cloudflare DNS and tunnel routes
- THEN those hostnames are used for route creation
- AND repository files and Terraform defaults do not contain the concrete hostname values
