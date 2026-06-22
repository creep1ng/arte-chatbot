# Delta for ECR CD Promotion

## ADDED Requirements

### Requirement: Production Hostname Input Pass-through

The deploy workflow MUST pass API, frontend, and admin hostnames to Terraform from GitHub Secrets/equivalent. Values SHOULD be sensitive deploy inputs to avoid repo exposure; DNS records MAY be public.

#### Scenario: Secrets supply hostnames

- GIVEN external deploy config contains service hostnames
- WHEN the production deploy workflow runs Terraform
- THEN Terraform receives API, frontend, and admin hostname inputs
- AND workflow source does not hardcode them

### Requirement: GitHub Variable Backend Runtime Config Pass-through

The deploy workflow MUST pass non-sensitive backend config to Terraform as `TF_VAR_backend_runtime_environment_variables` from `vars.PROD_BACKEND_RUNTIME_ENV_JSON || '{}'`. Secrets MUST stay in secret ARNs, Secrets Manager, or SSM.

#### Scenario: Variable supplies config

- GIVEN GitHub Variables define `PROD_BACKEND_RUNTIME_ENV_JSON` as a JSON object of string values
- WHEN the production deploy workflow runs Terraform
- THEN `TF_VAR_backend_runtime_environment_variables` contains that JSON object

#### Scenario: Missing variable defaults safely

- GIVEN `PROD_BACKEND_RUNTIME_ENV_JSON` is not defined
- WHEN the production deploy workflow runs Terraform
- THEN `TF_VAR_backend_runtime_environment_variables` is set to `{}`

#### Scenario: Secrets not in Variables

- GIVEN backend requires API keys, tunnel tokens, or other sensitive values
- WHEN deploy configuration is prepared
- THEN those secrets SHALL be referenced from secret ARNs, Secrets Manager, or SSM

## MODIFIED Requirements

### Requirement: CI and Evaluation Gate Before Promotion

Images MUST be promoted to deployable ECR tags only after CI, health checks, and evaluation succeed.
(Previously: tags were ECS-deployable.)

#### Scenario: Gate promotes images

- GIVEN backend, frontend, and admin images build successfully
- AND tests, health checks, and evaluation pass
- WHEN the CI workflow reaches the promotion step
- THEN immutable image tags are pushed or promoted in ECR

#### Scenario: Evaluation blocks promotion

- GIVEN the evaluation harness fails
- WHEN the CI workflow continues to deployment-related steps
- THEN no deployable production image tag is promoted
- AND no deploy command is triggered

### Requirement: Production Deploys Only From Main

Production deployment MUST run only from merge or push to `main`. Pull requests MAY build/test candidates but MUST NOT deploy production.
(Previously: deployment meant ECS updates.)

#### Scenario: Main deploys production

- GIVEN CI runs on `main`
- AND all gates pass
- WHEN the deployment job executes
- THEN the production EC2 Compose host is instructed to deploy the promoted ECR tags
- AND Cloudflare URL health checks pass

#### Scenario: PR skips production

- GIVEN CI runs for a pull request branch
- WHEN all build and evaluation gates pass
- THEN production deployment is skipped

### Requirement: Immutable Image and Task Definition Promotion

Deployments MUST reference immutable image IDs or SHA tags, and the deploy target MUST retain rollback metadata.
(Previously: registered ECS task revisions.)

#### Scenario: SHA image deployed

- GIVEN a successful `main` build creates images for a commit SHA
- WHEN the deploy job runs the production deploy command
- THEN backend, frontend, and admin containers reference matching SHA-based ECR tags

#### Scenario: Rollback target identifiable

- GIVEN a deployment has completed
- WHEN rollback is needed
- THEN the previous image tag or Compose release metadata can be identified

### Requirement: Deployment Credentials and Permissions

The CD workflow MUST use short-lived AWS credentials and least-privilege permissions for ECR promotion, SSM deploys, EC2/SSM discovery, and required Secrets Manager actions.
(Previously: permissions included ECS/IAM/logs/SSM/secrets.)

#### Scenario: Workflow uses OIDC

- GIVEN GitHub Actions starts a deployment on `main`
- WHEN AWS credentials are configured
- THEN the workflow assumes the deployment role through OIDC or another short-lived mechanism
- AND static long-lived AWS keys are not required

#### Scenario: Excess permission not required

- GIVEN the deployment role is scoped to deployment resources
- WHEN the workflow pushes images and invokes the host deploy command
- THEN it completes without requiring administrator-wide AWS permissions
