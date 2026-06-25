# Delta for ECS Runtime Configuration

## ADDED Requirements

### Requirement: Lambda Role S3 and State Access

The Lambda backend MUST use its execution role and AWS default credential provider chain for S3 and DynamoDB access, without static AWS keys.
Deployment and preview roles that run smoke checks MUST also have least-privilege DynamoDB read permissions needed to verify state persistence, including `dynamodb:Query` and `dynamodb:GetItem` on scoped state tables.

#### Scenario: Lambda reads S3 with role credentials

- GIVEN the Lambda role allows the required S3 reads
- WHEN the backend reads catalog or PDF objects
- THEN credentials come from the execution role
- AND no static AWS access key is required

#### Scenario: Lambda persists chatbot state

- GIVEN the Lambda role allows the configured state table operations
- WHEN chat state is read or written
- THEN the request uses IAM-scoped DynamoDB access

#### Scenario: Deploy role verifies persisted state

- GIVEN preview, staging, or production smoke checks require persisted-session evidence
- WHEN the deploy role runs the DynamoDB persistence check
- THEN it can call `Query` or `GetItem` on the scoped state table
- AND it does not require broad administrator permissions

## MODIFIED Requirements

### Requirement: Secrets and Configuration Sources

Secrets MUST be injected or resolved from AWS Secrets Manager or SSM SecureString for ECS tasks and Lambda runtime. Runtime secret ARN JSON and KMS ARN JSON used by deployment or preview workflows MUST be read from GitHub Secrets, not GitHub Variables. Non-sensitive runtime configuration SHOULD be provided through SSM Parameter Store, Terraform-managed environment variables, Lambda configuration, or task definition configuration. Lambda runtime MUST NOT load `.env.deploy` as a secret file; that file MAY only supply local/manual deployment inputs and MUST NOT be committed.
(Previously: Secrets and non-sensitive config were scoped to ECS task definitions and task configuration.)

#### Scenario: Secret injected at task startup

- GIVEN `OPENAI_API_KEY`, `CHAT_API_KEY`, or a Cloudflare tunnel token is required
- WHEN Terraform renders the ECS task definition
- THEN the value is referenced from Secrets Manager or SSM SecureString
- AND the plaintext secret is not committed to the repository

#### Scenario: Secret available to Lambda runtime

- GIVEN `OPENAI_API_KEY` or `CHAT_API_KEY` is required by Lambda
- WHEN Terraform renders Lambda configuration
- THEN the value is referenced or resolved from SSM or Secrets Manager
- AND plaintext secrets are not stored in code, package files, or committed env files

#### Scenario: Workflow reads secret ARN JSON from GitHub Secrets

- GIVEN the workflow needs runtime secret ARN JSON or KMS ARN JSON for Lambda configuration
- WHEN GitHub Actions renders Terraform inputs for preview, staging, or production
- THEN the JSON is read from GitHub Secrets
- AND GitHub Variables are used only for non-sensitive names, URLs, feature flags, or resource identifiers

#### Scenario: Non-sensitive config published

- GIVEN `AWS_BUCKET_NAME`, public API URL, or public frontend/admin URL is required by the runtime
- WHEN Terraform applies the environment configuration
- THEN ECS or Lambda receives the value through runtime configuration or a parameter reference
