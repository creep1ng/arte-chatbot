# Proposal: Admin Panel Chat UI Integration

## Intent

Make the test Chat UI available only as an authenticated admin-panel feature, while preserving conversation history, datasheet visibility, split-message rendering, and every existing admin feature.

## Scope

### In Scope
- Add an authenticated `/admin/chat` workbench in `admin-panel/` with the referenced ChatGPT-like layout: recent/generated conversations in a left sidebar, restored history on selection, right-aligned highlighted user bubbles, larger left/main assistant responses, and a bottom composer.
- Apply a design-system/theme refresh for the admin Chat UI using Smoky Black `#0F0F0F` and Amber `#FFC200` as primary colors, supported by Dark Silver `#736F72`, Platinum `#D8DDDE`, and Caribbean Green `#09BC8A`.
- Use an admin-authenticated backend proxy/equivalent so the browser never stores `CHAT_API_KEY`.
- Persist Chat UI conversation history immediately in admin-scoped browser storage with capped, secret-free metadata.
- Render split responses from `messages` when present, falling back to `response`.
- Show `Ver fichas técnicas` when sources exist; open a modal listing deduped fichas from `source_documents` and use admin S3 download/open flows.
- Remove/disable the standalone `frontend/` service as an access path.
- Add regression tests for chat behavior and preservation of current admin routes.

### Out of Scope
- Image generation or multimodal response support.
- Server-side cross-device chat history beyond existing logs.
- Rich datasheet snippets unless backend/catalog metadata is already available.

## Capabilities

### New Capabilities
- `admin-chat-workbench`: Authenticated admin Chat UI, secure chat proxy, local conversation history, source datasheet modal, split-message rendering, and no standalone Chat UI access.

### Modified Capabilities
- `ecs-runtime-configuration`: Runtime URLs/origins must reflect the admin panel as the single Chat UI browser surface, avoiding direct browser `CHAT_API_KEY` usage.
- `ecr-cd-promotion`: Image build/promotion/deploy expectations may need to stop treating the removed standalone Chat UI as an independently promoted UI service.

## Approach

Implement `/admin/chat` inside Next.js admin-panel as a feature route and sidebar item without changing existing admin pages. Add admin-protected backend chat proxy endpoints that reuse current chat processing, buffer polling, escalation metadata, token metrics, `source_documents`, and split-message fields. Keep conversation state in admin local storage, render datasheets from source paths, apply the required admin Chat UI theme as a future spec/design input, and retire the separate frontend service from Compose/deployment access.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `admin-panel/app/admin/*` | Modified | Add chat route/navigation, preserve current routes. |
| `admin-panel/components/*`, `lib/*` | New/Modified | Chat UI, theme tokens, types, storage, datasheet modal, API client. |
| `backend/main.py` or admin router | Modified | Admin-authenticated chat proxy/buffer endpoints. |
| `backend/app/admin_s3.py` | Reused | Presigned datasheet access. |
| `frontend/`, `docker-compose.yml` | Modified/Removed | Disable standalone Chat UI access path. |
| Tests | Modified | Admin route regressions, source modal, split messages. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Existing admin features regress | Med | Route-level regression tests and no layout rewrite. |
| API key exposure | Med | Admin proxy; do not persist chat secrets. |
| Source metadata is path-only | Med | Modal shows path/filename; snippets optional. |
| Split responses still render as one bubble | Med | Spec/test `messages` precedence. |

## Rollback Plan

Revert the admin chat route/proxy and restore the previous `frontend` service/image configuration. Existing admin routes remain unaffected because integration is additive behind `/admin/chat`.

## Dependencies

- Existing admin authentication and `POST /admin/s3/presigned-download`.
- Backend `ChatResponse.messages`, `source_documents`, and buffer-result contract.

## Success Criteria

- [ ] `/admin/chat` is the only supported Chat UI access path.
- [ ] Current admin features remain reachable and tested.
- [ ] Conversations restore from recent history after reload.
- [ ] Datasheet button/modal appears only when sources exist.
- [ ] Split responses render as multiple assistant messages.
