# Runtime Configuration Specification

## Purpose

Define how deployed runtimes receive credentials, secrets, public URLs, CORS
origins, S3 access, and serverless state configuration without static production
keys. The current backend production runtime is Lambda; ECS/Fargate language is
legacy-only unless explicitly scoped to non-production or archived artifacts.

## Requirements

### Requirement: Runtime Role S3 and State Access

Runtime S3 and DynamoDB access MUST use the deployed runtime's IAM role and the
AWS default credential provider chain. The backend MUST NOT require static AWS
access keys in environment variables. Deployment and preview roles that run smoke
checks MUST also have least-privilege DynamoDB read permissions needed to verify
state persistence, including `dynamodb:Query` and `dynamodb:GetItem` on scoped
state tables.

#### Scenario: Backend reads S3 with role credentials

- GIVEN the backend runtime role allows the required S3 bucket and object actions
- AND no static `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` is configured in
  the runtime environment
- WHEN the backend reads `index/catalog_index.json` or a product PDF
- THEN the AWS SDK obtains credentials from the runtime IAM role
- AND the request succeeds

#### Scenario: Lambda writes durable state with role credentials

- GIVEN the Lambda execution role allows the configured DynamoDB state table
- WHEN the backend reads or writes session, buffer, token, ownership, or rate
  counter state
- THEN the AWS SDK obtains credentials from the Lambda execution role
- AND no static AWS key fallback is used

#### Scenario: Deploy role verifies persisted state

- GIVEN preview, staging, or production smoke checks require persisted-session evidence
- WHEN the deploy role runs the DynamoDB persistence check
- THEN it can call `Query` or `GetItem` on the scoped state table
- AND it does not require broad administrator permissions

#### Scenario: Missing runtime role permission fails safely

- GIVEN the backend runtime role lacks access to the configured bucket or state
  table
- WHEN the backend attempts to read catalog data
- THEN the request fails with an authorization error
- AND no fallback to hardcoded or committed credentials is used

### Requirement: Secrets and Configuration Sources

Secrets MUST be injected or resolved from AWS Secrets Manager or SSM
SecureString references authorized by IAM. Runtime secret ARN JSON and KMS ARN
JSON used by deployment or preview workflows MUST be read from GitHub Secrets,
not GitHub Variables. Non-sensitive runtime configuration SHOULD be provided
through Terraform-managed Lambda environment variables, SSM Parameter Store, or
equivalent deployed-runtime configuration. `.env.deploy` MAY provide local/manual
Terraform inputs but MUST NOT be committed or loaded as a Lambda runtime secret
file.

#### Scenario: Secret available at runtime startup

- GIVEN `OPENAI_API_KEY` or `CHAT_API_KEY` is required
- WHEN Terraform renders Lambda configuration
- THEN the value is referenced from Secrets Manager or SSM SecureString
- AND the plaintext secret is not committed to the repository or packaged in the
  Lambda artifact

#### Scenario: Workflow reads secret ARN JSON from GitHub Secrets

- GIVEN the workflow needs runtime secret ARN JSON or KMS ARN JSON for Lambda configuration
- WHEN GitHub Actions renders Terraform inputs for preview, staging, or production
- THEN the JSON is read from GitHub Secrets
- AND GitHub Variables are used only for non-sensitive names, URLs, feature flags, or resource identifiers

#### Scenario: Non-sensitive config published

- GIVEN `AWS_BUCKET_NAME`, public API URL, or public frontend/admin URL is
  required by the runtime
- WHEN Terraform applies the environment configuration
- THEN the deployed runtime receives the value through Lambda configuration,
  runtime configuration, or a parameter reference

### Requirement: Configured CORS Origins

The backend MUST accept configured frontend and admin origins through environment
or runtime configuration. Production CORS MUST NOT default to a wildcard origin,
and local development origins SHOULD remain supported.

#### Scenario: Deployed UI can call API

- GIVEN the backend is deployed in production
- AND Terraform provides the allowed frontend/admin origins
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
the backend Lambda, frontend, and admin runtime configuration.

#### Scenario: Frontend receives API URL

- GIVEN the frontend/admin runtime starts
- WHEN its runtime configuration is generated
- THEN it receives the public API Gateway custom-domain URL
- AND browser calls target the deployed API hostname

#### Scenario: Backend receives UI origins

- GIVEN frontend/admin hostnames are declared in Terraform
- WHEN backend Lambda configuration is rendered
- THEN the corresponding origins are included in the backend allowed-origin
  configuration
