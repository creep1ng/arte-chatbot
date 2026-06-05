# Delta for ECS Runtime Configuration

## ADDED Requirements

### Requirement: Backend Runtime Environment Overrides

Terraform MUST expose `backend_runtime_environment_variables` as `map(string)` default `{}`. Values MUST merge into backend non-secret env, stay strings for app casting, and MUST NOT carry secrets.

#### Scenario: Empty map preserves defaults

- GIVEN no backend runtime overrides are provided
- WHEN Terraform renders production backend environment configuration
- THEN infrastructure defaults remain present

#### Scenario: Map augments config

- GIVEN `backend_runtime_environment_variables` contains non-sensitive string values
- WHEN Terraform renders production backend environment configuration
- THEN those values are included in the backend non-secret environment

#### Scenario: App casts types

- GIVEN an override value encodes a boolean, number, list, or URL string
- WHEN the backend application loads runtime configuration
- THEN the application/Pydantic configuration layer SHALL perform type casting

## MODIFIED Requirements

### Requirement: Task Role S3 Access

Runtime S3 access MUST use the runtime AWS role and default credential chain. EC2 Compose containers MUST NOT require static AWS keys.
(Previously: used ECS task role.)

#### Scenario: Backend reads S3 via role

- GIVEN the EC2 instance role allows required S3 bucket/object actions
- AND no static `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` is configured in container environment
- WHEN the backend reads catalog data or a product PDF
- THEN the AWS SDK uses runtime role credentials

#### Scenario: Missing permission fails safely

- GIVEN the runtime role lacks access to the configured bucket
- WHEN the backend attempts to read catalog data
- THEN the request fails with an authorization error
- AND no hardcoded credential fallback is used

### Requirement: Secrets and Configuration Sources

Secrets MUST come from Secrets Manager or SSM SecureString at deploy/startup. Non-sensitive config SHOULD use Terraform host config, SSM Parameter Store, or Compose env.
(Previously: used ECS task definitions.)

#### Scenario: Secret injected at startup

- GIVEN an API key or tunnel token is required
- WHEN production services start on the Compose host
- THEN the value is read from Secrets Manager or SSM SecureString

#### Scenario: Non-secret config published

- GIVEN bucket name or public URLs are required
- WHEN Terraform applies the environment configuration
- THEN the Compose runtime receives the value through host or service configuration

### Requirement: Configured CORS Origins

The backend MUST accept Cloudflare frontend/admin origins through runtime config. Production CORS MUST NOT default to wildcard; local origins SHOULD remain supported.
(Previously: ECS task config provided origins.)

#### Scenario: Cloudflare UI calls API

- GIVEN the backend is deployed in production
- AND runtime provides allowed UI origins
- WHEN a browser request reaches the API with one of those origins
- THEN the backend includes the expected CORS response headers

#### Scenario: Wildcard forbidden in production

- GIVEN the backend is deployed in production
- WHEN no explicit allowed origins are configured
- THEN the backend MUST NOT fall back to `*`
- AND validation MUST fail safely

#### Scenario: Local development supported

- GIVEN a developer runs the backend locally
- WHEN a browser request uses a configured local development origin
- THEN the backend allows the origin without requiring Cloudflare hostnames

### Requirement: Deployment-published Runtime URLs

Terraform MUST publish public URLs and allowed origins for backend, frontend, and admin runtime. Production hostnames MUST come from external deploy inputs and MUST NOT be hardcoded in source defaults.
(Previously: Terraform published values to ECS config.)

#### Scenario: UI receives API URL

- GIVEN the frontend/admin container starts on the Compose host
- WHEN its runtime configuration is generated
- THEN it receives the public Cloudflare API URL

#### Scenario: Backend receives origins

- GIVEN frontend/admin Cloudflare hostnames are supplied through external inputs
- WHEN backend runtime configuration is generated
- THEN they are included in backend allowed-origin configuration
