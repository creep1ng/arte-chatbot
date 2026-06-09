# Delta for ECS Runtime Configuration

## MODIFIED Requirements

### Requirement: Configured CORS Origins

The backend MUST accept configured Cloudflare admin origins through environment
or runtime configuration for browser-facing chat and admin operations.
Production CORS MUST NOT default to a wildcard origin, and local development
admin origins SHOULD remain supported.
(Previously: allowed configured Cloudflare frontend and admin origins.)

#### Scenario: Cloudflare admin UI can call API

- GIVEN the backend is deployed in production
- AND Terraform provides the allowed Cloudflare admin origin
- WHEN a browser request reaches the API from that origin
- THEN the backend includes the expected CORS response headers
- AND the request is allowed

#### Scenario: Wildcard forbidden in production

- GIVEN the backend is deployed in production
- WHEN no explicit allowed origins are configured
- THEN the backend MUST NOT fall back to `*`
- AND startup or configuration validation MUST fail safely

#### Scenario: Local development remains supported

- GIVEN a developer runs the backend locally
- WHEN a browser request uses the configured local admin-panel origin
- THEN the backend allows the origin without requiring Cloudflare hostnames

### Requirement: Deployment-published Runtime URLs

Terraform MUST provide or publish the public URLs and allowed origins needed by
the backend and admin runtime configuration. The admin panel SHALL be the single
browser Chat UI surface, and runtime configuration MUST NOT require direct
browser use of `CHAT_API_KEY`.
(Previously: published URLs and origins for backend, frontend, and admin.)

#### Scenario: Admin panel receives API URL

- GIVEN the admin container starts in ECS
- WHEN its runtime configuration is generated
- THEN it receives the public Cloudflare API URL
- AND browser calls target the deployed API hostname

#### Scenario: Backend receives admin UI origins

- GIVEN admin Cloudflare hostnames are declared in Terraform
- WHEN backend task configuration is rendered
- THEN the corresponding origins are included in allowed-origin configuration

#### Scenario: Standalone Chat UI is not configured

- GIVEN production runtime configuration is rendered
- WHEN browser UI URLs and origins are published
- THEN no standalone Chat UI origin is required for customer-chat testing
- AND chat access is represented by the admin panel surface
