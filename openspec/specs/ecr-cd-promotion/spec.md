# ECR CD Promotion Specification

## Purpose

Define how CI builds, gates, promotes, and deploys container images to ECS using
ECR, with production deployment limited to `main`.

## Requirements

### Requirement: CI and Evaluation Gate Before Promotion

Images MUST be promoted to deployable ECR tags only after CI checks, health
checks, and the evaluation harness succeed.

#### Scenario: Successful gate promotes images

- GIVEN backend and frontend images build successfully
- AND tests, health checks, and evaluation pass
- WHEN the CI workflow reaches the promotion step
- THEN immutable image tags are pushed or promoted in ECR
- AND those tags are eligible for ECS deployment

#### Scenario: Failed evaluation blocks promotion

- GIVEN the evaluation harness fails
- WHEN the CI workflow continues to deployment-related steps
- THEN no deployable production image tag is promoted
- AND no ECS service update is triggered

### Requirement: Production Deploys Only From Main

Production ECS deployment MUST run only from a merge or push to `main`. Pull
requests MAY build and test candidate images but MUST NOT deploy production.

#### Scenario: Main branch deploys production

- GIVEN CI runs on `main`
- AND all gates pass
- WHEN the deployment job executes
- THEN ECS task definitions are registered with the promoted ECR image tags
- AND production ECS services are updated

#### Scenario: Pull request does not deploy production

- GIVEN CI runs for a pull request branch
- WHEN all build and evaluation gates pass
- THEN production ECS deployment is skipped
- AND any candidate image tags are not treated as production releases

### Requirement: Immutable Image and Task Definition Promotion

Deployments MUST reference immutable image identifiers or SHA-based tags, and the
workflow MUST register new ECS task definition revisions before updating
services.

#### Scenario: SHA-tagged image deployed

- GIVEN a successful `main` build creates images for a commit SHA
- WHEN the deploy job renders task definitions
- THEN backend and frontend containers reference the matching SHA-based ECR tags
- AND ECS services update to the new task definition revisions

#### Scenario: Rollback target remains identifiable

- GIVEN a deployment has completed
- WHEN rollback is needed
- THEN the previous image tag or task definition revision can be identified
- AND the ECS service can be reverted to that known version

### Requirement: Deployment Credentials and Permissions

The CD workflow MUST use short-lived AWS credentials and least-privilege
permissions for ECR, ECS, IAM pass-role, logs, SSM, and Secrets Manager actions
required by deployment.

#### Scenario: Workflow authenticates with OIDC

- GIVEN GitHub Actions starts a deployment on `main`
- WHEN AWS credentials are configured
- THEN the workflow assumes the deployment role through OIDC or another
  short-lived credential mechanism
- AND static long-lived AWS keys are not required for production deployment

#### Scenario: Excess permission not required

- GIVEN the deployment role is scoped to the Arte Chatbot deployment resources
- WHEN the workflow pushes images and updates ECS services
- THEN it completes without requiring administrator-wide AWS permissions
