# Chatwoot deployment runbook

This runbook explains how to connect the ARTE backend to a self-hosted Chatwoot AgentBot safely. Start with the happy path, verify with mocked/local checks first, and only then capture staging screenshots from a real Chatwoot workspace.

> Current scope: backend webhook, Redis-backed state, mocked CI coverage, and operational rollout. Admin-panel Chatwoot configuration is intentionally deferred until the `feature/admin-panel-slice-*` work is integrated coherently.

## Quick path

1. Configure Chatwoot AgentBot and webhook events.
2. Set backend environment variables and GitHub staging secrets.
3. Deploy with `CHATWOOT_ENABLED=true` only after the webhook URL is reachable.
4. Run the smoke checklist below.
5. Roll back immediately with `CHATWOOT_ENABLED=false` if webhook processing is unhealthy.

## Prerequisites

| Requirement | Why it matters | Status to confirm |
|-------------|----------------|-------------------|
| Self-hosted Chatwoot workspace | Source of AgentBot webhooks and Application API calls | Workspace URL is reachable over HTTPS |
| Backend HTTPS host | Chatwoot must call the webhook publicly | `https://<backend-host>/health` responds |
| Redis 7+ | Stores idempotency, buffers, mappings, and history cache | `/health/chatwoot` reports Redis healthy or degraded intentionally |
| AgentBot access token | Allows bot responses through Chatwoot API | Token is stored only as a secret |
| Webhook HMAC secret | Prevents unsigned webhook processing | Secret is generated and stored in backend config |
| Existing backend secrets | `/chat` and LLM tooling still require them | `OPENAI_API_KEY`, `CHAT_API_KEY`, AWS vars are configured where needed |

## Chatwoot AgentBot setup

### 1. Create the AgentBot

1. In Chatwoot, open **Settings → Integrations → Agent Bots**.
2. Create an AgentBot for ARTE.
3. Copy the AgentBot access token.
4. Assign the AgentBot to the target inbox, usually the WhatsApp inbox.

### 2. Configure the webhook

| Field | Value |
|-------|-------|
| Webhook URL | `https://<backend-host>/webhook/chatwoot` |
| Signature/HMAC secret | Same value as `CHATWOOT_WEBHOOK_SECRET` |
| Events to enable | `message_created`, `conversation_created`, `conversation_status_changed` |

The backend intentionally awaits webhook processing instead of scheduling `BackgroundTasks`. That means handler failures return HTTP 500 so Chatwoot can retry the webhook; a premature HTTP 200 would hide failed state updates or missed bot responses.

### 3. Confirm event filtering expectations

| Chatwoot message | Backend behavior |
|------------------|------------------|
| Incoming contact message | Creates/reuses session mapping, buffers, and can trigger bot processing |
| Private message | Ignored |
| Outgoing message | Ignored to avoid bot self-loops |
| AgentBot/self message | Ignored to avoid recursive replies |
| Human-agent message | Flushes/cancels active bot buffer so the human response wins |

## Backend environment variables

| Variable | Required | Example | Notes |
|----------|----------|---------|-------|
| `CHATWOOT_ENABLED` | Yes | `true` | Rollback switch: set `false` to disable webhook processing. |
| `CHATWOOT_API_URL` | Yes | `https://chatwoot.example.com` | Chatwoot base URL, no trailing slash preferred. |
| `CHATWOOT_AGENT_BOT_TOKEN` | Yes | secret | Application API token; never commit. |
| `CHATWOOT_ACCOUNT_ID` | Yes | `1` | Numeric account ID used in API paths and Redis namespace. |
| `CHATWOOT_INBOX_ID` | Recommended | `7` | Inbox used for initial channel mapping. |
| `CHATWOOT_WEBHOOK_SECRET` | Yes | secret | Shared HMAC secret for webhook verification. |
| `CHATWOOT_HANDOFF_TEAM_ID` | Optional | `55` | Enables team assignment during escalation. |
| `CHATWOOT_BOT_LABEL` | Optional | `bot` | Label configuration remains env-driven for now. |
| `CHATWOOT_ESCALATED_LABEL` | Optional | `escalated` | Label applied during human handoff. |
| `REDIS_URL` | Yes | `redis://redis:6379/0` | Redis state backend. |
| `REDIS_PASSWORD` | If used | secret | Required only for secured Redis deployments. |
| `REDIS_SOCKET_TIMEOUT` | Optional | `2.0` | Keep low to preserve graceful degradation. |
| `REDIS_MAX_CONNECTIONS` | Optional | `20` | Tune with traffic. |

## GitHub staging notes

Use a protected GitHub Environment such as `staging` before enabling workflows that touch real Chatwoot.

| Secret or variable | Mocked CI | Real staging |
|--------------------|-----------|--------------|
| `CHATWOOT_API_URL` | Dummy value in CI | Real Chatwoot URL |
| `CHATWOOT_AGENT_BOT_TOKEN` | Dummy value in CI | Real AgentBot token |
| `CHATWOOT_ACCOUNT_ID` | Dummy value in CI | Real numeric account ID |
| `CHATWOOT_INBOX_ID` | Dummy value in CI | Real inbox ID |
| `CHATWOOT_WEBHOOK_SECRET` | Dummy value in CI | Real webhook secret |
| `OPENAI_API_KEY` | Dummy for mocked Chatwoot CI | Real LLM key if staging invokes LLM |
| `CHAT_API_KEY` | Dummy for mocked Chatwoot CI | Real backend API key |

Mocked CI MUST remain the default PR gate. Real Chatwoot end-to-end checks are not currently in CI because credentials and a stable external Chatwoot connection are not available yet.

## Smoke test checklist

Run these checks after deployment. They do not require a CI workflow.

### Backend checks

- [ ] `GET https://<backend-host>/health` returns healthy baseline status.
- [ ] `GET https://<backend-host>/health/chatwoot` returns `healthy` or an explicitly understood `degraded` status.
- [ ] `POST /webhook/chatwoot` with an invalid signature returns `401`.
- [ ] `POST /webhook/chatwoot` with `CHATWOOT_ENABLED=false` returns `503`.
- [ ] Logs show `chatwoot_event_received` for a test webhook.
- [ ] Logs do not expose `CHATWOOT_AGENT_BOT_TOKEN` or `CHATWOOT_WEBHOOK_SECRET`.

### Chatwoot checks

- [ ] AgentBot is assigned to the intended inbox.
- [ ] Webhook URL is exactly `https://<backend-host>/webhook/chatwoot`.
- [ ] Enabled events are exactly `message_created`, `conversation_created`, and `conversation_status_changed`.
- [ ] A new conversation creates a session mapping in Redis.
- [ ] Incoming contact message receives a bot response in Chatwoot.
- [ ] Private/outgoing AgentBot messages do not trigger additional bot responses.
- [ ] Human-agent reply during a pending bot buffer prevents duplicate bot follow-up.

### Local mocked command

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

## Rollback

Fast rollback is configuration-only:

```bash
CHATWOOT_ENABLED=false
```

Expected rollback behavior:

| Area | Result |
|------|--------|
| `/webhook/chatwoot` | Returns `503` and does not parse or dispatch payloads |
| `/chat` | Existing standalone API remains available |
| Redis state | Existing keys can expire naturally |
| Chatwoot AgentBot | Can remain configured, but backend will not process webhooks |

If Chatwoot keeps retrying after rollback, temporarily disable the Chatwoot webhook or AgentBot assignment in Chatwoot.

## Limitations and deferred work

| Limitation | Current decision |
|------------|------------------|
| Attachments | Not supported yet; text content is processed first, attachment-only messages are not a production-ready flow. |
| Admin-panel Chatwoot config | Deferred. Existing admin panel work lives on `feature/admin-panel-slice-*` and must be integrated coherently rather than patched into this branch. |
| Real Chatwoot e2e in CI | Deferred until stable credentials, staging workspace, and protected environment approval are available. |
| BackgroundTasks ack | Not used for webhook dispatch because retry safety is currently more important than early ack semantics. |

## Screenshot checklist for rollout evidence

Capture these screenshots when real Chatwoot access exists:

- [ ] AgentBot list showing the ARTE AgentBot enabled.
- [ ] AgentBot details with token redacted.
- [ ] Inbox assignment showing the AgentBot connected to the target inbox.
- [ ] Webhook configuration showing URL and enabled events.
- [ ] Backend deployment environment showing Chatwoot variables present, with secret values hidden.
- [ ] `/health/chatwoot` response in staging.
- [ ] Chatwoot conversation where an incoming contact message gets one bot response.
- [ ] Chatwoot conversation where a private/outgoing message does not cause a bot loop.
- [ ] Human handoff example showing status/label/team behavior if escalation is enabled.

## References

- `docs/guides/chatwoot_testing_ci.md` — mocked CI and local command guide.
- `backend/app/chatwoot_handler.py` — webhook dispatch, filtering, mapping, and processing seam.
- `backend/main.py` — webhook HMAC validation and retry-safe awaited dispatch.
