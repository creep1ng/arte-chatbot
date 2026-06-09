# Delta for ECR CD Promotion

## MODIFIED Requirements

### Requirement: CI and Evaluation Gate Before Promotion

Images MUST be promoted to deployable ECR tags only after CI checks, health
checks, and the evaluation harness succeed. Promotion MUST cover backend and
admin-panel images required for the integrated admin Chat UI, and MUST NOT treat
a removed standalone Chat UI as an independently deployable UI service.
(Previously: promoted backend and frontend images after gates succeeded.)

#### Scenario: Successful gate promotes images

- GIVEN backend and admin-panel images build successfully
- AND tests, health checks, and evaluation pass
- WHEN the CI workflow reaches the promotion step
- THEN immutable image tags are pushed or promoted in ECR
- AND those tags are eligible for ECS deployment

#### Scenario: Failed evaluation blocks promotion

- GIVEN the evaluation harness fails
- WHEN the CI workflow continues to deployment-related steps
- THEN no deployable production image tag is promoted
- AND no ECS service update is triggered

#### Scenario: Standalone Chat UI is not promoted

- GIVEN the standalone Chat UI is no longer a supported browser surface
- WHEN deployable UI images are selected for promotion
- THEN only the admin-panel UI image is treated as deployable for chat access

### Requirement: Immutable Image and Task Definition Promotion

Deployments MUST reference immutable image identifiers or SHA-based tags, and the
workflow MUST register new ECS task definition revisions before updating
services. Task definitions SHALL reference backend and admin-panel containers
needed by the integrated Chat UI and SHALL NOT require a separate standalone
Chat UI container for browser access.
(Previously: task definitions referenced backend and frontend containers.)

#### Scenario: SHA-tagged image deployed

- GIVEN a successful `main` build creates images for a commit SHA
- WHEN the deploy job renders task definitions
- THEN backend and admin-panel containers reference matching SHA-based ECR tags
- AND ECS services update to the new task definition revisions

#### Scenario: Rollback target remains identifiable

- GIVEN a deployment has completed
- WHEN rollback is needed
- THEN the previous image tag or task definition revision can be identified
- AND the ECS service can be reverted to that known version

#### Scenario: No standalone Chat UI task required

- GIVEN the integrated admin Chat UI is deployed
- WHEN ECS services are updated
- THEN chat browser access is provided by the admin-panel service
- AND no separate standalone Chat UI service is required
