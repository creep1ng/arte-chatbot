# Serverless Chatbot Backend Specification

## Purpose

Define the Lambda backend target for the existing chatbot without redesigning its product behavior.

## Requirements

### Requirement: Lambda Chatbot Runtime

The backend MUST run on AWS Lambda without VPC, NAT Gateway, Fargate, EC2, or always-on backend capacity.

#### Scenario: Health endpoint works on serverless runtime

- GIVEN the Lambda backend is deployed
- WHEN a client calls `/health`
- THEN the response reports service health without requiring ECS or EC2

#### Scenario: Production target forbids VPC dependency

- GIVEN backend production infrastructure is planned
- WHEN deployment is validated
- THEN Lambda has no VPC attachment or NAT Gateway requirement

### Requirement: Functional Chat Endpoint Preservation

The system MUST preserve authenticated `/chat`, S3 datasheet lookup, File Inputs, tool calling, and conversation logging behavior unless a serverless-safety exception is explicitly documented.

#### Scenario: Authenticated chat uses product documents

- GIVEN a valid chat request and API key
- WHEN the user asks about a product datasheet
- THEN the backend can read the S3 catalog/PDF and answer using File Inputs

#### Scenario: Unauthorized chat is rejected

- GIVEN a missing or invalid chat API key
- WHEN `/chat` is called
- THEN the request is rejected before model or storage access

### Requirement: Durable Lambda-safe State

Conversation history, session ownership, user profile, token totals, and required shared counters MUST be stored outside Lambda process memory.

#### Scenario: Session survives cold start

- GIVEN a conversation has prior persisted state
- WHEN a later request is handled by a cold Lambda environment
- THEN the backend restores the required session state

#### Scenario: Concurrent ownership is safe

- GIVEN two requests attempt conflicting ownership updates
- WHEN state is written
- THEN only the valid conditional update succeeds

### Requirement: Deployment Secrets and Local Deploy Inputs

Runtime secrets MUST come from IAM-authorized SSM Parameter Store or Secrets Manager references. `.env.deploy` MAY provide local/manual deployment inputs but MUST NOT be committed or used as a Lambda runtime secret file.

#### Scenario: Lambda resolves runtime secret by reference

- GIVEN OpenAI and chat secrets are configured in AWS
- WHEN Lambda starts
- THEN it reads only authorized secret references or injected values

#### Scenario: Package excludes local secret files

- GIVEN a deployment package is produced
- WHEN package contents are checked
- THEN `.env`, `.env.deploy`, and plaintext credentials are absent

### Requirement: Staging, Promotion, and Rollback

CI/CD MUST package, test, deploy isolated staging, run smoke/evaluation checks, promote the same package to production, and support rollback to a previous Lambda version or alias.

#### Scenario: Staging validates direct chatbot endpoint

- GIVEN a candidate package passes tests
- WHEN staging deploys
- THEN `/health` and authenticated `/chat` are validated on a direct non-production endpoint

#### Scenario: Production rollback restores previous version

- GIVEN production promotion causes a failed smoke check or incident
- WHEN rollback runs
- THEN traffic returns to the previous Lambda version/alias

### Requirement: Ephemeral Pull Request Preview Stack

Pull request previews MUST use an ephemeral Lambda/API Gateway/DynamoDB stack under the `infra/terraform/envs/pr-preview` contract. Preview stacks MUST be deployable only for same-repository pull requests, MUST use GitHub Secrets for runtime JSON inputs, and MUST be cleaned up when the pull request is closed or the preview is no longer needed.

#### Scenario: Same-repository pull request deploys preview

- GIVEN a pull request originates from the repository, not a fork
- WHEN preview deployment is gated
- THEN the workflow may deploy the `pr-preview` Terraform environment
- AND resource names, state, logs, API endpoints, and DynamoDB tables are scoped to the pull request

#### Scenario: Forked pull request cannot access preview secrets

- GIVEN a pull request originates from a fork
- WHEN the preview workflow evaluates the event
- THEN deployment is skipped before reading runtime secret JSON or assuming deployment credentials

#### Scenario: Pull request preview cleanup is bounded

- GIVEN a same-repository pull request preview exists
- WHEN the pull request closes or cleanup is requested
- THEN the workflow destroys only the matching preview stack
- AND production and staging resources are not targeted

### Requirement: Preview Smoke and Persistence Checks

Preview validation MUST run deterministic smoke/evaluation checks against the preview endpoint, resolve `CHAT_API_KEY` from the runtime secret ARN JSON stored in GitHub Secrets, validate File Inputs with the smaller LONGi datasheet prompt, and verify DynamoDB persistence for the preview session.

#### Scenario: Preview smoke resolves chat key from runtime secret ARN

- GIVEN GitHub Secrets contain runtime secret ARN JSON for the preview environment
- WHEN preview smoke checks run
- THEN the workflow resolves the `CHAT_API_KEY` value from the configured AWS secret ARN
- AND the plaintext key is not stored in GitHub Variables or committed files

#### Scenario: Preview smoke uses deterministic File Inputs prompt

- GIVEN the preview endpoint is healthy
- WHEN smoke sends the File Inputs prompt for the smaller LONGi PDF
- THEN the response includes source documents from the datasheet path
- AND the check avoids large-PDF prompts that risk Lambda timeout during preview validation

#### Scenario: Preview smoke verifies DynamoDB persistence

- GIVEN authenticated preview chat succeeds
- WHEN the smoke script checks preview state
- THEN it queries DynamoDB for the generated session partition
- AND at least one persisted state row is found

### Requirement: Direct File Input Response

After `leer_ficha_tecnica` returns a File Input answer, the backend MUST be able to return that answer directly when it is sufficient for the user request instead of requiring a redundant final LLM synthesis call.

#### Scenario: Datasheet answer avoids redundant final model call

- GIVEN the model calls `leer_ficha_tecnica`
- AND the File Input response contains the final datasheet answer
- WHEN the backend prepares the chat response
- THEN it may return the File Input answer directly
- AND it records source documents and token usage without making an additional synthesis call that could exceed the Lambda timeout

### Requirement: Roadmap Items Are Non-blocking

API Gateway/WAF rate limiting, DynamoDB precision limiters, SQS/EventBridge/Step Functions buffering, async jobs, dashboards, and tracing SHOULD be tracked as future evolution and MUST NOT be required for the current migration.

#### Scenario: Current phase avoids workflow redesign mandate

- GIVEN the first Lambda migration is planned
- WHEN scope is checked
- THEN roadmap workflow services are optional future work
