# Archive Report: Low-Cost EC2 Compose Exposure

**Change**: `low-cost-ec2-compose-exposure`
**Archived on**: 2026-06-22
**Artifact store**: OpenSpec
**Final status**: Superseded by `migrate-backend-to-lambda-serverless`

The EC2 Compose + Cloudflare Tunnel deployment path is preserved as history, but
it is no longer an active production backend source of truth. Production now uses
Lambda behind API Gateway HTTP API, with rollback limited to Lambda alias/version
movement.

## Why archived

| Area | Current decision |
|---|---|
| Backend runtime | Lambda/API Gateway/DynamoDB replaced the EC2 Compose host. |
| Ingress | API Gateway custom domain plus Cloudflare DNS replaced Cloudflare Tunnel runtime. |
| Deploy path | Lambda package promotion replaced SSM Run Command Compose deploys. |
| Rollback | Previous Lambda alias target replaced EC2/Fargate route rollback. |

## Active source of truth after archive

- `openspec/changes/migrate-backend-to-lambda-serverless/`
- `openspec/specs/serverless-chatbot-backend/spec.md`
- `docs/deployment.md`
- `docs/adr/009.md`

## Archive contents

- `proposal.md`
- `exploration.md`
- `design.md`
- `tasks.md`
- `apply-progress.md`
- `verify-report.md`
- `archive-report.md`
- `specs/`
- `state.yaml`

## SDD cycle status

Complete and superseded. The active change directory was moved to
`openspec/changes/archive/2026-06-22-low-cost-ec2-compose-exposure/` so current
validation does not treat EC2 Compose/Cloudflare Tunnel as an active production
path.
