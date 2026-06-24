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

### Requirement: Roadmap Items Are Non-blocking

API Gateway/WAF rate limiting, DynamoDB precision limiters, SQS/EventBridge/Step Functions buffering, async jobs, dashboards, and tracing SHOULD be tracked as future evolution and MUST NOT be required for the current migration.

#### Scenario: Current phase avoids workflow redesign mandate

- GIVEN the first Lambda migration is planned
- WHEN scope is checked
- THEN roadmap workflow services are optional future work
