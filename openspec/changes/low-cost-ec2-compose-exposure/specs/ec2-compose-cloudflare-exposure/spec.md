# EC2 Compose Cloudflare Exposure Specification

## Purpose

Define production public exposure through one EC2 Docker Compose host and one Cloudflare Tunnel, without ALB, NAT Gateway, or public inbound application ports.

## Requirements

### Requirement: Latest Ubuntu LTS AMI Discovery

The production Compose host MUST use the latest Ubuntu LTS AMI resolved during infrastructure planning or apply. The default deployment path MUST NOT require a fixed `ami_id` value checked into source.

#### Scenario: Default AMI selected dynamically

- GIVEN production infrastructure is planned without an explicit AMI override
- WHEN the host image is resolved
- THEN the selected image is the latest matching Ubuntu LTS image for the target region
- AND no fixed AMI ID is required in repository configuration

#### Scenario: Stale AMI ID not hardcoded

- GIVEN the cloud provider publishes a newer Ubuntu LTS image
- WHEN Terraform resolves the Compose host image again
- THEN the plan can select the newer LTS image without source-code changes

### Requirement: External Service Hostname Inputs

Production API, frontend, and admin hostnames MUST be supplied through sensitive Terraform inputs, GitHub Secrets, or an equivalent external channel. Source code and Terraform defaults MUST NOT hardcode the service hostnames; created DNS records MAY still be public by design.

#### Scenario: Hostnames supplied externally

- GIVEN deploy-time hostname inputs are available outside the repository
- WHEN Terraform configures Cloudflare routes and runtime URLs
- THEN API, frontend, and admin hostnames are read from those inputs
- AND no default service hostname is committed in source

#### Scenario: DNS visibility is not treated as secret storage

- GIVEN Terraform creates Cloudflare DNS records for service hostnames
- WHEN DNS is queried publicly after deployment
- THEN the records MAY be visible
- AND the repository still MUST NOT expose hardcoded hostname values

### Requirement: Production Compose Tunnel Exposure

The production system MUST run backend, frontend, admin, and Cloudflare Tunnel connector services on one Docker Compose host. Public traffic MUST enter through Cloudflare Tunnel only, and application ports MUST NOT be exposed publicly.

#### Scenario: Public hostnames served through one tunnel

- GIVEN production backend, frontend, admin, and tunnel services are running on the Compose host
- WHEN Cloudflare receives requests for the configured API, app, and admin hostnames
- THEN one tunnel routes each hostname to the matching Compose service origin
- AND no ALB, NLB, or NAT Gateway is required

#### Scenario: Direct app port access blocked

- GIVEN the EC2 host has public internet egress
- WHEN a client attempts inbound access to backend or UI container ports
- THEN the security boundary MUST deny public inbound application traffic

### Requirement: Compose Service Origins

Cloudflare Tunnel routes MUST target Docker Compose service DNS names, not `localhost`, because the connector runs as a separate container.

#### Scenario: Backend origin uses Compose DNS

- GIVEN the tunnel configuration includes the production API hostname
- WHEN the connector resolves the origin
- THEN it MUST target the backend service on its internal Compose port

#### Scenario: Unknown hostname returns 404

- GIVEN Cloudflare forwards a hostname not declared for production
- WHEN the request reaches the tunnel rules
- THEN the tunnel MUST return a 404-style fallback response

### Requirement: Accepted Single-host Tradeoff

Production MAY accept one EC2 host as a temporary single point of failure to meet the low-cost target, but rollback to the prior ECS/Fargate exposure path MUST remain possible until cutover is verified.

#### Scenario: Cutover fails before acceptance

- GIVEN EC2 Compose deployment is unhealthy after cutover validation
- WHEN rollback is initiated
- THEN operators can restore traffic to the previous production exposure path
