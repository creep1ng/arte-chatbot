# Fargate Cloudflare Ingress Specification

## Purpose

Define how ECS Fargate services expose private HTTP origins through Cloudflare
Tunnel without an ALB, while keeping each connector able to reach every origin it
serves.

## Requirements

### Requirement: Same-task Cloudflare Tunnel Sidecars

The system MUST deploy each public Fargate origin with a `cloudflared` sidecar in
the same ECS task as the origin container, and the tunnel route MUST target the
origin through `localhost`.

#### Scenario: Backend API exposed through localhost sidecar

- GIVEN a backend ECS task definition contains `backend` and `cloudflared`
  containers
- WHEN Terraform applies the backend ingress configuration
- THEN the public API hostname routes to `http://localhost:8000`
- AND the backend task can serve traffic without an ALB

#### Scenario: Frontend or admin exposed through localhost sidecar

- GIVEN a frontend or admin ECS task definition contains the origin container and
  `cloudflared`
- WHEN Terraform applies the UI ingress configuration
- THEN the public UI hostname routes to `http://localhost:3000`
- AND the connector does not require access to another ECS task to reach the
  origin

### Requirement: Scoped Tunnel Ownership

The system MUST use a separate Cloudflare Tunnel scope per service or hostname
group unless every connector replica for that tunnel can reach every configured
origin.

#### Scenario: Separate backend and frontend tunnels

- GIVEN backend and frontend run as separate ECS services with same-task
  localhost origins
- WHEN public hostnames are configured
- THEN the API hostname is attached only to a backend-reachable tunnel
- AND the frontend/admin hostnames are attached only to a UI-reachable tunnel

#### Scenario: Shared tunnel rejected when origins are unreachable

- GIVEN one tunnel has backend and frontend hostnames
- AND a connector replica can reach only the backend localhost origin
- WHEN Terraform validates or plans the ingress configuration
- THEN the configuration MUST fail or require an explicit central-connector mode
  where all origins are reachable

### Requirement: Terraform-managed Cloudflare Routes

Terraform MUST manage Cloudflare tunnel resources, hostname routes, and DNS
records for deployed services, while keeping tunnel tokens out of plaintext
outputs.

#### Scenario: Public hostname provisioned

- GIVEN a service declares a public hostname and local origin URL
- WHEN Terraform is applied
- THEN the corresponding Cloudflare route and DNS record are created or updated
- AND the tunnel token is referenced through a secret source

#### Scenario: Token not exposed

- GIVEN Terraform stores or passes a tunnel token to ECS
- WHEN Terraform outputs are inspected
- THEN the raw token value MUST NOT appear in non-sensitive outputs

### Requirement: Fargate Network and Health Configuration

Terraform MUST provision ECS services, task definitions, logs, security groups,
and outbound connectivity required for Cloudflare and AWS dependencies.

#### Scenario: Connector can establish outbound tunnel

- GIVEN a Fargate service is deployed in the configured VPC
- WHEN the `cloudflared` sidecar starts
- THEN it can reach Cloudflare over outbound HTTPS
- AND application containers can reach required AWS services

#### Scenario: ECS health protects unhealthy origins

- GIVEN an origin container becomes unhealthy
- WHEN ECS evaluates task health
- THEN the service replaces the unhealthy task according to the task definition
  health configuration
