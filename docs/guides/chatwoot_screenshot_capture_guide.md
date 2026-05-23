# Chatwoot screenshot capture guide

Use this guide when real Chatwoot access exists. The goal is to produce rollout
evidence that a maintainer can verify quickly without exposing secrets or
customer data.

## Quick path

1. Capture configuration screenshots first: AgentBot, webhook, inbox, account,
   labels, and handoff team.
2. Capture behavior screenshots second: health check, bot reply, ignored
   private/outgoing message, and human handoff.
3. Redact secrets and customer data before attaching screenshots to docs or
   issues.
4. Link screenshots from GitHub issue #186 and the final runbook update.

## Redaction rules

| Must hide | Why |
|-----------|-----|
| AgentBot token | Allows sending messages through Chatwoot API. |
| Webhook HMAC secret | Allows signing spoofed webhooks. |
| Customer phone numbers and names | PII. |
| Message contents from real customers | PII/business context. Use a test contact. |
| GitHub secret values | Secrets must be names-only in screenshots. |

Prefer a dedicated staging/test contact so screenshots can show realistic flow
without exposing customer data.

## Screenshot set

### 1. AgentBot details

**Capture:** Chatwoot AgentBot detail page.

**Must show:**

- AgentBot name, e.g. `ARTE Chatbot`.
- Enabled/active state.
- Assigned inbox if visible.
- Token field redacted.

**Use it to verify:** `CHATWOOT_AGENT_BOT_TOKEN` exists and belongs to the bot.

### 2. Webhook configuration

**Capture:** AgentBot/webhook configuration screen.

**Must show:**

- URL: `https://<backend-host>/webhook/chatwoot`.
- Events: `message_created`, `conversation_created`,
  `conversation_status_changed`.
- HMAC/signature secret redacted.

**Use it to verify:** Chatwoot calls the correct endpoint. Do not use `/chat`.

### 3. WhatsApp inbox assignment

**Capture:** Inbox settings for the WhatsApp inbox.

**Must show:**

- Inbox name.
- Channel type/provider.
- Inbox ID if visible, or URL containing the ID.
- AgentBot assignment.

**Use it to verify:** `CHATWOOT_INBOX_ID` and channel profile assumptions.

### 4. Account ID source

**Capture:** Browser URL or account settings showing the account ID.

**Must show:**

- A URL segment such as `/accounts/1/` or equivalent settings display.

**Use it to verify:** `CHATWOOT_ACCOUNT_ID`.

### 5. Handoff team

**Capture:** Team settings for the handoff target.

**Must show:**

- Team name.
- Team ID if visible, or URL containing the ID.
- Team members can be blurred if needed.

**Use it to verify:** `CHATWOOT_HANDOFF_TEAM_ID`.

### 6. Labels

**Capture:** Labels/settings page.

**Must show:**

- Bot label, e.g. `bot`.
- Escalation label, e.g. `escalated`.
- Technical label, e.g. `technical`.

**Use it to verify:** label env values match Chatwoot labels.

### 7. GitHub secrets names

**Capture:** Repository or environment secrets list.

**Must show names only:**

- `CHATWOOT_API_URL`
- `CHATWOOT_AGENT_BOT_TOKEN`
- `CHATWOOT_ACCOUNT_ID`
- `CHATWOOT_INBOX_ID`
- `CHATWOOT_WEBHOOK_SECRET`
- `CHATWOOT_HANDOFF_TEAM_ID` when assignment is enabled

**Never show:** secret values.

### 8. `/health/chatwoot`

**Capture:** terminal or API client response.

**Healthy example:**

```json
{
  "status": "healthy",
  "chatwoot_enabled": true,
  "redis": "healthy",
  "chatwoot_api": "configured"
}
```

**Use it to verify:** backend config and Redis readiness.

### 9. Incoming contact message response

**Capture:** Chatwoot conversation with a staging contact.

**Must show:**

- One incoming contact message.
- Exactly one bot response.
- No duplicate bot messages after retry window.

**Use it to verify:** webhook → buffer/session → bot response flow.

### 10. Private/outgoing message does not loop

**Capture:** Chatwoot conversation after an internal/private note or outgoing
agent message.

**Must show:**

- The private/outgoing message.
- No follow-up bot reply caused by that message.

**Use it to verify:** self-loop filtering.

### 11. Human handoff

**Capture:** Escalated conversation.

**Must show:**

- Conversation status changed to open.
- Escalation label applied.
- Team assigned when configured.
- Handoff message sent to the contact.

**Use it to verify:** escalation handler behavior.

### 12. Rollback state

**Capture:** backend response with `CHATWOOT_ENABLED=false`.

**Expected:**

```json
{
  "detail": "Chatwoot integration disabled"
}
```

from `POST /webhook/chatwoot`, and `/chat` remains available.

## Attachment checklist for the documentation issue

- [ ] AgentBot details screenshot.
- [ ] Webhook URL/events screenshot.
- [ ] WhatsApp inbox assignment screenshot.
- [ ] Account ID evidence screenshot.
- [ ] Handoff team screenshot.
- [ ] Labels screenshot.
- [ ] GitHub secrets names screenshot.
- [ ] `/health/chatwoot` screenshot.
- [ ] Contact message → bot response screenshot.
- [ ] Private/outgoing no-loop screenshot.
- [ ] Human handoff screenshot.
- [ ] Rollback screenshot.

## Where to link screenshots

Attach screenshots to GitHub issue #186 first. After review, add
selected redacted images to the runbook or link the issue from the runbook,
depending on repository documentation size limits and maintainer preference.
