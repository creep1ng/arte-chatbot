# ECS Runtime Configuration Specification

## Purpose

Define how deployed ECS tasks receive credentials, secrets, public URLs, CORS
origins, and S3 access without static production keys.

## Requirements

### Requirement: Task Role S3 Access

Runtime S3 access MUST use the ECS task role and the AWS default credential
provider chain. Deployed tasks MUST NOT require static AWS access keys in
environment variables.

#### Scenario: Backend reads S3 with task role credentials

- GIVEN the backend task role allows the required S3 bucket and object actions
- AND no static `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` is configured in
  the task environment
- WHEN the backend reads `index/catalog_index.json` or a product PDF
- THEN the AWS SDK obtains credentials from the ECS task role
- AND the request succeeds

#### Scenario: Missing task role permission fails safely

- GIVEN the backend task role lacks access to the configured bucket
- WHEN the backend attempts to read catalog data
- THEN the request fails with an authorization error
- AND no fallback to hardcoded or committed credentials is used

### Requirement: Secrets and Configuration Sources

Secrets MUST be injected from AWS Secrets Manager or SSM SecureString through ECS
task definitions. Non-sensitive runtime configuration SHOULD be provided through
SSM Parameter Store, Terraform-managed environment variables, or task
definition configuration.

#### Scenario: Secret injected at task startup

- GIVEN `OPENAI_API_KEY`, `CHAT_API_KEY`, or a Cloudflare tunnel token is required
- WHEN Terraform renders the ECS task definition
- THEN the value is referenced from Secrets Manager or SSM SecureString
- AND the plaintext secret is not committed to the repository

#### Scenario: Non-sensitive config published

- GIVEN `AWS_BUCKET_NAME`, public API URL, or public frontend/admin URL is
  required by the runtime
- WHEN Terraform applies the environment configuration
- THEN ECS receives the value through task configuration or a parameter reference

### Requirement: Configured CORS Origins

The backend MUST accept configured Cloudflare frontend and admin origins through
environment or runtime configuration. Production CORS MUST NOT default to a
wildcard origin, and local development origins SHOULD remain supported.

#### Scenario: Cloudflare UI can call API

- GIVEN the backend is deployed in production
- AND Terraform provides the allowed Cloudflare frontend/admin origins
- WHEN a browser request reaches the API with one of those origins
- THEN the backend includes the expected CORS response headers
- AND the request is allowed

#### Scenario: Wildcard forbidden in production

- GIVEN the backend is deployed in production
- WHEN no explicit allowed origins are configured
- THEN the backend MUST NOT fall back to `*`
- AND startup or configuration validation MUST fail safely

#### Scenario: Local development remains supported

- GIVEN a developer runs the backend locally
- WHEN a browser request uses `http://localhost:3000` or another configured local
  development origin
- THEN the backend allows the origin without requiring Cloudflare hostnames

### Requirement: Deployment-published Runtime URLs

Terraform MUST provide or publish the public URLs and allowed origins needed by
the backend, frontend, and admin runtime configuration.

#### Scenario: Frontend receives API URL

- GIVEN the frontend/admin container starts in ECS
- WHEN its runtime configuration is generated
- THEN it receives the public Cloudflare API URL
- AND browser calls target the deployed API hostname

#### Scenario: Backend receives UI origins

- GIVEN frontend/admin Cloudflare hostnames are declared in Terraform
- WHEN backend task configuration is rendered
- THEN the corresponding origins are included in the backend allowed-origin
  configuration
