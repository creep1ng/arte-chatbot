# Delta for Serverless Chatbot Backend

## ADDED Requirements

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
