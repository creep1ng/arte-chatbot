# Artifact CD Promotion Specification

## Purpose

Define how CI builds, gates, promotes, and deploys immutable artifacts, including
the backend Lambda package and frontend/admin container images, with production
deployment limited to `main`.

## Requirements

### Requirement: CI and Evaluation Gate Before Promotion

Images and Lambda packages MUST be promoted to deployable releases only after CI
checks, health checks, package checks, and the evaluation harness succeed.

#### Scenario: Successful gate promotes images

- GIVEN backend and frontend images build successfully
- AND tests, health checks, and evaluation pass
- WHEN the CI workflow reaches the promotion step
- THEN immutable image tags are pushed or promoted in ECR
- AND those tags are eligible for the remaining image-based delivery paths

#### Scenario: Successful gate promotes Lambda package

- GIVEN the backend Lambda package builds reproducibly
- AND tests, package scan, health checks, and evaluation pass
- WHEN the CI workflow reaches promotion
- THEN the same immutable package is eligible for staging and production Lambda
  aliases

#### Scenario: Failed evaluation blocks promotion

- GIVEN the evaluation harness fails
- WHEN the CI workflow continues to deployment-related steps
- THEN no deployable production image tag or Lambda package is promoted
- AND no production service update or Lambda alias promotion is triggered

### Requirement: Production Deploys Only From Main

Production deployment MUST run only from a merge or push to `main`. Pull
requests MAY build and test candidate artifacts but MUST NOT deploy production.

#### Scenario: Main branch deploys production

- GIVEN CI runs on `main`
- AND all gates pass
- WHEN the deployment job executes
- THEN the backend Lambda alias is updated only with the promoted package
- AND any image-based production release paths use promoted immutable image tags

#### Scenario: Pull request does not deploy production

- GIVEN CI runs for a pull request branch
- WHEN all build and evaluation gates pass
- THEN production deployment is skipped
- AND candidate artifacts are not treated as production releases

### Requirement: Immutable Image and Task Definition Promotion

Deployments MUST reference immutable image identifiers, SHA-based tags, or
immutable Lambda package/version identifiers. The workflow MUST publish Lambda
versions or register task definition revisions before production traffic is
updated.

#### Scenario: SHA-tagged image deployed

- GIVEN a successful `main` build creates images for a commit SHA
- WHEN the deploy job renders task definitions
- THEN backend and frontend containers reference the matching SHA-based ECR tags
- AND any image-based services update to the new task definition revisions

#### Scenario: Lambda version promoted

- GIVEN a successful `main` build creates a Lambda package for a commit SHA
- WHEN production promotion runs
- THEN traffic points to the published version or alias for that package

#### Scenario: Rollback target remains identifiable

- GIVEN a deployment has completed
- WHEN rollback is needed
- THEN the previous image tag, task definition revision, Lambda version, or alias
  target can be identified
- AND traffic can be reverted to that known version

### Requirement: Deployment Credentials and Permissions

The CD workflow MUST use short-lived AWS credentials and least-privilege
permissions for ECR, Lambda, API Gateway, DynamoDB, IAM pass-role, logs, SSM, and
Secrets Manager actions required by deployment.

#### Scenario: Workflow authenticates with OIDC

- GIVEN GitHub Actions starts a deployment on `main`
- WHEN AWS credentials are configured
- THEN the workflow assumes the deployment role through OIDC or another
  short-lived credential mechanism
- AND static long-lived AWS keys are not required for production deployment

#### Scenario: Excess permission not required

- GIVEN the deployment role is scoped to Arte Chatbot deployment resources
- WHEN the workflow promotes images or Lambda packages
- THEN it completes without requiring administrator-wide AWS permissions
