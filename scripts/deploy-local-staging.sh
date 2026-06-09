#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$ROOT_DIR/infra/terraform/envs/local-staging"
DOMAIN_NAME="artesolutions.com.co"
AWS_REGION="us-east-1"
PLAN_ONLY=false
DESTROY=false
AUTO_APPROVE=false
STAGING_ID=""
BACKEND_TAG=""
ADMIN_TAG=""
EXPIRES_AT=""

usage() {
  cat <<'EOF'
Usage: scripts/deploy-local-staging.sh \
  --staging-id <id> \
  --backend-tag <sha-or-pr-tag> \
  --admin-tag <sha-or-pr-tag> \
  [--domain-name artesolutions.com.co] [--aws-region us-east-1] \
  [--expires-at 2026-06-05T12:00:00Z] [--plan-only] [--destroy] [--auto-approve]

Local staging is developer-run only. It rejects CI, production hostnames/names,
implicit image tags, and expirations more than three days from now.
EOF
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --staging-id) STAGING_ID="${2:-}"; shift 2 ;;
    --backend-tag) BACKEND_TAG="${2:-}"; shift 2 ;;
    --admin-tag) ADMIN_TAG="${2:-}"; shift 2 ;;
    --domain-name) DOMAIN_NAME="${2:-}"; shift 2 ;;
    --aws-region) AWS_REGION="${2:-}"; shift 2 ;;
    --expires-at) EXPIRES_AT="${2:-}"; shift 2 ;;
    --plan-only) PLAN_ONLY=true; shift ;;
    --destroy) DESTROY=true; shift ;;
    --auto-approve) AUTO_APPROVE=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

if [[ "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" ]]; then
  fail "local staging cannot run in CI"
fi

[[ -n "$STAGING_ID" ]] || fail "--staging-id is required"
[[ -n "$BACKEND_TAG" ]] || fail "--backend-tag is required"
[[ -n "$ADMIN_TAG" ]] || fail "--admin-tag is required"

if ! [[ "$STAGING_ID" =~ ^[a-z0-9][a-z0-9-]{1,30}$ ]]; then
  fail "staging id must be 2-31 chars using lowercase letters, numbers, and hyphens"
fi

if [[ "$STAGING_ID" =~ ^(api|app|admin|prod|production|main)$ || "$STAGING_ID" =~ prod|production ]]; then
  fail "staging id would collide with production naming"
fi

validate_tag() {
  local label="$1"
  local value="$2"
  if ! [[ "$value" =~ ^(sha-[0-9a-fA-F]{7,40}|pr-[0-9]+-sha-[0-9a-fA-F]{7,40}|local-[a-zA-Z0-9._-]+)$ ]]; then
    fail "$label tag must be an explicit immutable ECR tag (sha-<sha>, pr-<number>-sha-<sha>, or local-<name>)"
  fi
}

validate_tag "backend" "$BACKEND_TAG"
validate_tag "admin" "$ADMIN_TAG"

if [[ "$DOMAIN_NAME" != "artesolutions.com.co" ]]; then
  fail "domain-name must remain artesolutions.com.co for Arte Cloudflare staging"
fi

if [[ -z "$EXPIRES_AT" ]]; then
  EXPIRES_AT="$(python - <<'PY'
from datetime import UTC, datetime, timedelta
print((datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"))
PY
)"
fi

python - "$EXPIRES_AT" <<'PY' || fail "expiration must be no later than 3 days from now and formatted as YYYY-MM-DDTHH:MM:SSZ"
from datetime import UTC, datetime, timedelta
import sys
expires_at = datetime.strptime(sys.argv[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
now = datetime.now(UTC)
if expires_at <= now or expires_at > now + timedelta(days=3, minutes=1):
    raise SystemExit(1)
PY

BACKEND_HOSTNAME="staging-chatbot-api-${STAGING_ID}.${DOMAIN_NAME}"
ADMIN_HOSTNAME="staging-chatbot-admin-${STAGING_ID}.${DOMAIN_NAME}"

for hostname in "$BACKEND_HOSTNAME" "$ADMIN_HOSTNAME"; do
  case "$hostname" in
    "api.${DOMAIN_NAME}"|"app.${DOMAIN_NAME}"|"admin.${DOMAIN_NAME}")
      fail "production URL/name rejected for local staging: $hostname"
      ;;
  esac
done

required_tf_vars=(
  TF_VAR_vpc_id
  TF_VAR_private_subnet_ids
  TF_VAR_cloudflare_account_id
  TF_VAR_cloudflare_zone_id
  TF_VAR_backend_tunnel_secret
  TF_VAR_admin_tunnel_secret
  TF_VAR_backend_ecr_repository_url
  TF_VAR_admin_ecr_repository_url
  TF_VAR_backend_ecr_repository_arn
  TF_VAR_admin_ecr_repository_arn
  TF_VAR_aws_bucket_name
  TF_VAR_backend_runtime_secret_arns
  CLOUDFLARE_API_TOKEN
)

for var_name in "${required_tf_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    fail "$var_name is required for local staging; export it or source a local-only deploy env file"
  fi
done

STATE_DIR="$ROOT_DIR/.terraform/local-staging/${STAGING_ID}"
STATE_PATH="$STATE_DIR/terraform.tfstate"
PLAN_PATH="$STATE_DIR/tfplan"
mkdir -p "$STATE_DIR"

export TF_VAR_staging_id="$STAGING_ID"
export TF_VAR_domain_name="$DOMAIN_NAME"
export TF_VAR_aws_region="$AWS_REGION"
export TF_VAR_backend_image_tag="$BACKEND_TAG"
export TF_VAR_admin_image_tag="$ADMIN_TAG"
export TF_VAR_expiration_at="$EXPIRES_AT"

echo "Local staging: $STAGING_ID"
echo "Hostnames: $BACKEND_HOSTNAME, $ADMIN_HOSTNAME"
echo "Expires at: $EXPIRES_AT"

terraform -chdir="$TF_DIR" init -reconfigure -backend-config="path=$STATE_PATH"

if [[ "$DESTROY" == "true" ]]; then
  terraform -chdir="$TF_DIR" plan -destroy -out="$PLAN_PATH"
elif [[ "$PLAN_ONLY" == "true" ]]; then
  terraform -chdir="$TF_DIR" plan -out="$PLAN_PATH"
  exit 0
else
  terraform -chdir="$TF_DIR" plan -out="$PLAN_PATH"
fi

if [[ "$AUTO_APPROVE" == "true" ]]; then
  terraform -chdir="$TF_DIR" apply -auto-approve "$PLAN_PATH"
else
  terraform -chdir="$TF_DIR" apply "$PLAN_PATH"
fi
