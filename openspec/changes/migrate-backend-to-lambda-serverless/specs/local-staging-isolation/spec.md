# Delta for Local Staging Isolation

## ADDED Requirements

### Requirement: Serverless Staging Resources

Serverless staging MUST use isolated Lambda, API exposure, DynamoDB, secret/config namespace, log group, names, tags, and state from production.

#### Scenario: Serverless staging deploys isolated resources

- GIVEN a developer deploys serverless staging
- WHEN infrastructure is applied
- THEN resources use non-production names and state
- AND production Lambda, API routes, tables, and secrets are not targeted

#### Scenario: Staging cleanup is bounded

- GIVEN serverless staging is destroyed or expires
- WHEN cleanup runs
- THEN staging compute/API resources are removed
- AND staging state uses TTL or explicit deletion controls

### Requirement: Direct Chatbot Endpoint Validation

Staging MUST expose a quick direct non-production chatbot endpoint for validation without impacting production.

#### Scenario: Direct endpoint validates health and chat

- GIVEN serverless staging has deployed
- WHEN smoke tests run against the staging endpoint
- THEN `/health` and authenticated `/chat` pass
- AND production URLs are not called

#### Scenario: File Inputs path is validated

- GIVEN staging chat uses an approved catalog/data source
- WHEN a datasheet-backed question is sent
- THEN S3 PDF retrieval and File Inputs behavior are validated

#### Scenario: IAM denial fails safely

- GIVEN staging lacks a required S3, DynamoDB, or secret permission
- WHEN the protected operation is attempted
- THEN validation fails with an authorization error
- AND no fallback credential is used

## MODIFIED Requirements

### Requirement: Isolated Tokens, Secrets, and Parameters

Local staging MUST NOT reuse production Cloudflare tunnel tokens, Secrets Manager secrets, SSM parameters, API credentials, or Lambda runtime secret/config namespaces.
(Previously: Isolation covered Cloudflare tunnel tokens, Secrets Manager secrets, SSM parameters, and API credentials.)

#### Scenario: Local staging token is separate

- GIVEN local staging needs a Cloudflare tunnel token
- WHEN Terraform or the local staging runner resolves the token
- THEN it uses a local-staging-specific secret source
- AND the production tunnel token is not referenced

#### Scenario: Parameter prefix remains isolated

- GIVEN local staging task or Lambda configuration is generated
- WHEN SSM or Secrets Manager references are resolved
- THEN every reference uses the local staging prefix or namespace
- AND production parameter paths are rejected

#### Scenario: Lambda secret namespace remains isolated

- GIVEN serverless staging resolves OpenAI or chat credentials
- WHEN Lambda configuration is rendered
- THEN references use staging-approved names or ARNs
- AND production secret references are rejected by default
