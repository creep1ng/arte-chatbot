# Local Staging Isolation Specification

## Purpose

Define guardrails for local-only staging so experiments cannot reuse or mutate
production CI, Terraform state, Cloudflare tunnels, AWS names, or parameters.
Staging SHOULD deploy the same ECR image candidate that passed PR CI/evaluation.

## Requirements

### Requirement: Local-only Staging Execution

Local staging MUST be explicitly marked local-only and MUST NOT run from CI or
production deployment workflows. CI MAY build, validate, and promote PR
candidate images to ECR, but CI MUST NOT create or update staging infrastructure.

#### Scenario: Local staging runs from developer machine

- GIVEN a developer explicitly selects the local staging environment
- WHEN they apply or deploy local staging resources
- THEN Terraform uses local-staging names, variables, and state
- AND production resources are not targeted

#### Scenario: CI blocks local staging

- GIVEN a CI workflow attempts to use the local staging environment
- WHEN staging guard checks execute
- THEN the workflow fails before mutating AWS or Cloudflare resources

#### Scenario: PR image candidate is available for local staging

- GIVEN PR CI builds and evaluates a backend or frontend image successfully
- WHEN the promotion step runs
- THEN the image is pushed to ECR with an immutable PR or SHA candidate tag
- AND local staging may later deploy that tag from a developer machine

### Requirement: ECR-backed Staging Deployments

Local staging deploys SHOULD consume an explicit ECR image tag produced by CI for
the PR. A developer MAY push a local image to ECR and pass that tag to staging,
but this is optional and MUST be explicit.

#### Scenario: Developer deploys PR candidate from ECR

- GIVEN CI promoted a PR candidate image tag to ECR
- WHEN a developer runs the local staging deploy script with that tag
- THEN Terraform renders the staging task definition with the provided ECR image
- AND no production service is updated

#### Scenario: Developer-provided local image tag

- GIVEN a developer builds and pushes a local image tag to ECR
- WHEN they pass that tag to the local staging deploy script
- THEN staging uses that explicit tag
- AND the tag is not promoted as a production release

### Requirement: Staging Expiration Metadata

Local staging SHOULD record an expiration no later than three days after
creation, and tooling SHOULD make expired environments visible for cleanup.

#### Scenario: Staging records expiration

- GIVEN a local staging environment is created
- WHEN Terraform applies staging metadata
- THEN resources are tagged or parameterized with an expiration timestamp
- AND the expiration is no more than three days from creation

#### Scenario: Expired staging is identifiable

- GIVEN a staging environment is past its expiration timestamp
- WHEN cleanup tooling lists staging resources
- THEN the expired environment is clearly identified for destroy

### Requirement: Isolated Terraform State and Names

Local staging MUST use separate Terraform state, resource names, service names,
parameter paths, and tags from production.

#### Scenario: Distinct state selected

- GIVEN local staging Terraform is initialized
- WHEN the state backend or workspace is selected
- THEN it is distinct from production state
- AND production state cannot be selected by default

#### Scenario: Production names rejected

- GIVEN a local staging plan contains a production service name, tunnel name, or
  parameter path
- WHEN validation runs
- THEN the plan fails before apply

### Requirement: Isolated Tokens, Secrets, and Parameters

Local staging MUST NOT reuse production Cloudflare tunnel tokens, Secrets
Manager secrets, SSM parameters, or API credentials.

#### Scenario: Local staging token is separate

- GIVEN local staging needs a Cloudflare tunnel token
- WHEN Terraform or the local staging runner resolves the token
- THEN it uses a local-staging-specific secret source
- AND the production tunnel token is not referenced

#### Scenario: Parameter prefix remains isolated

- GIVEN local staging task configuration is generated
- WHEN SSM or Secrets Manager references are resolved
- THEN every reference uses the local staging prefix or namespace
- AND production parameter paths are rejected

### Requirement: No Production Mixing in Runtime Config

Local staging runtime configuration MUST make environment mixing visible and
fail fast when production hostnames, buckets, service names, or origins are used
without explicit approval.

#### Scenario: Production origin detected

- GIVEN local staging backend CORS origins are configured
- WHEN a production Cloudflare frontend/admin origin appears in the local staging
  allowed-origin list
- THEN validation fails before deployment

#### Scenario: Production bucket rejected by default

- GIVEN local staging S3 configuration is generated
- WHEN the configured bucket or prefix points at production data
- THEN deployment fails unless an explicit documented exception is provided

### Requirement: Unique Staging Public Hostnames

Local staging SHOULD expose each environment through a unique non-production
Cloudflare hostname derived from the staging identifier, such as
`staging-chatbot-<id>.example.com`. Local staging MUST NOT use the official
production service URL. Direct IPv4 access MAY be used only as a documented
fallback when Cloudflare hostname creation is unavailable.

#### Scenario: Staging uses unique hostname

- GIVEN a staging environment is created for a PR or candidate image
- WHEN Terraform applies Cloudflare routing
- THEN the public hostname includes the staging identifier
- AND it does not equal the production API, frontend, or admin hostname

#### Scenario: Production URL rejected

- GIVEN local staging route configuration references the official production URL
- WHEN validation runs
- THEN the deployment fails before mutating AWS or Cloudflare resources

#### Scenario: IPv4 fallback is explicit

- GIVEN Cloudflare staging hostname creation is unavailable
- WHEN a developer chooses direct IPv4 testing
- THEN the fallback is explicit and documented
- AND it does not weaken production hostname or tunnel isolation
