# Delta for ECR CD Promotion

## MODIFIED Requirements

### Requirement: CI and Evaluation Gate Before Promotion

Images and Lambda packages MUST be promoted to deployable releases only after CI checks, health checks, package checks, and the evaluation harness succeed.
(Previously: Promotion gates applied to ECR images for ECS deployment.)

#### Scenario: Successful gate promotes images

- GIVEN backend and frontend images build successfully
- AND tests, health checks, and evaluation pass
- WHEN the CI workflow reaches the promotion step
- THEN immutable image tags are pushed or promoted in ECR
- AND those tags are eligible for ECS deployment

#### Scenario: Successful gate promotes Lambda package

- GIVEN the Lambda package builds reproducibly and tests/evaluation pass
- WHEN the CI workflow reaches promotion
- THEN the same immutable package is eligible for staging and production

#### Scenario: Failed evaluation blocks promotion

- GIVEN the evaluation harness fails
- WHEN the CI workflow continues to deployment-related steps
- THEN no deployable production image tag or Lambda package is promoted
- AND no ECS service update or Lambda alias promotion is triggered

### Requirement: Production Deploys Only From Main

Production ECS or Lambda deployment MUST run only from a merge or push to `main`. Pull requests MAY build and test candidates but MUST NOT deploy production.
Same-repository pull requests MAY deploy an ephemeral preview stack after gates pass; forked pull requests MUST NOT deploy previews or read deployment secrets.
(Previously: Production deployment was limited to ECS from `main`.)

#### Scenario: Main branch deploys production

- GIVEN CI runs on `main`
- AND all gates pass
- WHEN the deployment job executes
- THEN ECS task definitions or Lambda aliases are updated with promoted artifacts

#### Scenario: Pull request does not deploy production

- GIVEN CI runs for a pull request branch
- WHEN all build and evaluation gates pass
- THEN production deployment is skipped
- AND candidate artifacts are not treated as production releases

#### Scenario: Same-repository pull request deploys only preview

- GIVEN CI runs for a same-repository pull request
- AND preview deployment is enabled
- WHEN package, tests, and evaluation gates pass
- THEN the workflow may deploy or update the pull-request preview stack
- AND no production alias or production route is updated

#### Scenario: Pull request preview cleanup runs on close

- GIVEN a pull-request preview stack exists
- WHEN the pull request is closed
- THEN the workflow destroys the matching preview environment
- AND cleanup does not require production deployment permissions beyond the preview-scoped resources

### Requirement: Immutable Image and Task Definition Promotion

Deployments MUST reference immutable image identifiers, SHA-based tags, or immutable Lambda package/version identifiers. The workflow MUST register ECS task definition revisions or publish Lambda versions before production traffic is updated.
(Previously: Deployments referenced immutable images and ECS task definition revisions.)

#### Scenario: SHA-tagged image deployed

- GIVEN a successful `main` build creates images for a commit SHA
- WHEN the deploy job renders task definitions
- THEN backend and frontend containers reference the matching SHA-based ECR tags
- AND ECS services update to the new task definition revisions

#### Scenario: Lambda version promoted

- GIVEN a successful `main` build creates a Lambda package for a commit SHA
- WHEN production promotion runs
- THEN traffic points to the published version or alias for that package

#### Scenario: Rollback target remains identifiable

- GIVEN a deployment has completed
- WHEN rollback is needed
- THEN the previous image tag, task definition revision, Lambda version, or alias target can be identified
- AND traffic can be reverted to that known version

### Requirement: Deployment Credentials and Permissions

The CD workflow MUST use short-lived AWS credentials and least-privilege permissions for ECR, ECS, Lambda, API Gateway, DynamoDB, IAM pass-role, logs, SSM, and Secrets Manager actions required by deployment.
(Previously: Permissions covered ECR, ECS, IAM pass-role, logs, SSM, and Secrets Manager.)

#### Scenario: Workflow authenticates with OIDC

- GIVEN GitHub Actions starts a deployment on `main`
- WHEN AWS credentials are configured
- THEN the workflow assumes the deployment role through OIDC or another short-lived mechanism
- AND static long-lived AWS keys are not required for production deployment

#### Scenario: Excess permission not required

- GIVEN the deployment role is scoped to Arte Chatbot deployment resources
- WHEN the workflow promotes images or Lambda packages
- THEN it completes without requiring administrator-wide AWS permissions

#### Scenario: Preview smoke can read state evidence

- GIVEN the preview workflow deploy role runs smoke checks after deployment
- WHEN it validates DynamoDB persistence for the generated chat session
- THEN the role allows scoped `dynamodb:Query` and `dynamodb:GetItem`
- AND the workflow fails if those reads are denied
