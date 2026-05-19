# Chatwoot mocked testing and CI

This project runs Chatwoot coverage with mocked dependencies by default. The
mocked suite validates webhook security, endpoint dispatch, Redis-backed state,
and escalation orchestration without connecting to a real Chatwoot instance.

## Quick path

```bash
# Mocked Chatwoot endpoint, scenario, security, and Redis integration suite
uv run pytest \
  backend/tests/test_chatwoot_auth.py \
  backend/tests/test_chatwoot_endpoints.py \
  backend/tests/test_chatwoot_scenarios.py \
  backend/tests/test_chatwoot_redis_integration.py

# Affected component suite around the Chatwoot integration
uv run pytest \
  backend/tests/test_channel_profile.py \
  backend/tests/test_config_provider.py \
  backend/tests/test_redis_cache.py \
  backend/tests/test_chatwoot_client.py \
  backend/tests/test_message_buffer_redis.py \
  backend/tests/test_session_manager_hybrid.py \
  backend/tests/test_escalation_handler.py \
  backend/tests/test_chatwoot_handler.py \
  backend/tests/test_chatwoot_auth.py \
  backend/tests/test_chatwoot_endpoints.py \
  backend/tests/test_chatwoot_scenarios.py \
  backend/tests/test_chatwoot_redis_integration.py
```

## CI-equivalent mocked command

The `test-chatwoot-integration` job in `.github/workflows/ci.yml` uses dummy
values only:

```bash
CHAT_API_KEY=test-chat-api-key \
OPENAI_API_KEY=test-openai-key \
CHATWOOT_ENABLED=true \
CHATWOOT_API_URL=https://chatwoot.test \
CHATWOOT_AGENT_BOT_TOKEN=test-token \
CHATWOOT_ACCOUNT_ID=1 \
CHATWOOT_INBOX_ID=7 \
CHATWOOT_WEBHOOK_SECRET=test-secret \
uv run pytest \
  backend/tests/test_chatwoot_auth.py \
  backend/tests/test_chatwoot_endpoints.py \
  backend/tests/test_chatwoot_scenarios.py \
  backend/tests/test_chatwoot_redis_integration.py
```

Mocked CI tests MUST NOT use real Chatwoot tokens, webhook secrets, or a real
Chatwoot API URL.

## GitHub secrets and variables

| Name | Required for mocked CI? | Required for real staging/e2e? | Notes |
|------|--------------------------|--------------------------------|-------|
| `CHAT_API_KEY` | No, dummy value is set by CI | Yes | Existing API auth secret. |
| `OPENAI_API_KEY` | No, dummy value is set by CI | Yes | Existing LLM secret. |
| `AWS_ROLE_ARN` | No | Yes | Existing GitHub OIDC role for evaluation/S3 workflows. |
| `AWS_BUCKET_NAME` | No | Yes | Existing S3 bucket name for evaluation/data workflows. |
| `CHATWOOT_API_URL` | No, dummy value is set by CI | Yes | Base URL for the real Chatwoot instance. |
| `CHATWOOT_AGENT_BOT_TOKEN` | No, dummy value is set by CI | Yes | AgentBot token. Never commit it. |
| `CHATWOOT_ACCOUNT_ID` | No, dummy value is set by CI | Yes | Numeric Chatwoot account ID. |
| `CHATWOOT_INBOX_ID` | No, dummy value is set by CI | Yes | Numeric inbox ID for the WhatsApp channel. |
| `CHATWOOT_WEBHOOK_SECRET` | No, dummy value is set by CI | Yes | HMAC shared secret. Never commit it. |
| `CHATWOOT_HANDOFF_TEAM_ID` | No | Optional | Required only when escalation assignment is enabled. |

## Real Chatwoot staging/e2e guardrail

Before enabling any workflow that calls a real Chatwoot API, configure a
protected GitHub Environment such as `staging`. Store the real Chatwoot secrets
there, require approval, and keep the mocked deterministic suite as the default
PR gate.
