# Design: Admin Panel Chat UI Integration

## Technical Approach

Add an authenticated `/admin/chat` workbench inside the existing Next.js admin panel, keeping `app/admin/layout.tsx` as the protected shell and adding only a sidebar item plus a new route. The browser will call admin-authenticated backend proxy endpoints, not `/chat` with `CHAT_API_KEY`. The UI ports the useful standalone behavior—session id, buffering, escalation lock, token metadata—but upgrades it to a ChatGPT-like admin layout with recent conversations, source datasheet modal, split assistant bubbles, and local, secret-free history.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Secure chat access | Add `/admin/chat` and `/admin/chat/buffer-result/{session_id}` under `admin_router`, protected by `verify_admin_key`, reusing `main._process_chat_message` and buffer helpers. | Browser calls `/chat` with stored `CHAT_API_KEY`. | Prevents chat secret exposure and keeps admin auth as the single browser access gate. |
| Admin UI shape | New `admin-panel/app/admin/chat/page.tsx` with feature components under `components/chat/`. | Rewrite admin layout or keep standalone `frontend/`. | Preserves all current admin routes and makes chat additive. |
| Conversation history | Persist capped conversations in `localStorage` under an admin-scoped key; store session id, title, timestamps, messages, sources, tokens, escalation state. | Use S3 logs for UI state. | Local history is immediate and works while logs are async/configurable; no secrets are persisted. |
| Visual system | Route-scoped dark workbench using Smoky Black `#0F0F0F`, Amber `#FFC200`, Dark Silver, Platinum, and Caribbean Green CSS variables/classes. | Replace global admin theme. | Delivers the requested production Chat UI without destabilizing existing admin screens. |
| Datasheets | Dedupe `source_documents` by `ruta`; show `Ver fichas técnicas` only when sources exist; call existing `/admin/s3/presigned-download`. | Backend enrichment before modal. | Current contract only guarantees paths and optional snippets, so modal must not depend on rich metadata. |

## Data Flow

```text
Admin user ─→ /admin/chat page ─→ adminFetch("/admin/chat")
                               └→ localStorage capped history
Backend /admin/chat ─→ verify_admin_key ─→ existing chat processing ─→ ChatResponse
Buffered response ─→ /admin/chat/buffer-result/{session_id} ─→ parsed ChatResponse
Sources button ─→ /admin/s3/presigned-download ─→ S3 PDF URL
```

## File Changes

| File | Action | Description |
|---|---|---|
| `backend/app/admin_chat.py` | Create | Admin proxy endpoints, schemas/imports, buffer polling wrapper, no `CHAT_API_KEY` browser dependency. |
| `backend/app/admin_router.py` | Modify | Include `chat_router`. |
| `backend/main.py` | Modify | Extract reusable chat/buffer helpers if needed; keep public `/chat` behavior unchanged. |
| `admin-panel/app/admin/layout.tsx` | Modify | Add Chat nav item; preserve existing items/routes. |
| `admin-panel/app/admin/chat/page.tsx` | Create | Authenticated chat workbench route. |
| `admin-panel/components/chat/*` | Create | Sidebar, thread, composer, message bubble, source modal, token/status badges. |
| `admin-panel/lib/types.ts` | Modify | Add `ChatRequest`, `ChatResponse`, `SourceDocument`, `BufferResultResponse`, local history types. |
| `admin-panel/lib/api.ts` | Modify | Export chat mutations/polling helpers via existing `adminFetch`. |
| `admin-panel/app/globals.css` or route module | Modify | Add route-scoped chat palette tokens/utilities. |
| `frontend/`, `docker-compose.yml` | Modify/Delete | Retire standalone Chat UI service/access path. |

## Interfaces / Contracts

```ts
type ChatRequest = { message: string; session_id?: string; is_final?: boolean };
type SourceDocument = { ruta: string; contenido_relevante?: string | null };
type ChatResponse = { response: string; session_id: string; source_documents: SourceDocument[]; messages: string[]; delays_ms: number[]; escalate: boolean; input_tokens?: number | null; output_tokens?: number | null; total_tokens?: number | null };
type BufferResultResponse = { status: "pending" | "ready" | "not_found"; session_id: string; result?: string | null };
```

Render assistant parts from `messages.length ? messages : [response]` for both direct and buffered responses.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Backend unit/integration | Admin proxy auth, no chat key header required, buffering result contract, split fields preserved. | Extend `backend/app/tests` or `backend/tests/test_chat.py` with FastAPI client tests. |
| Frontend unit | Route renders layout, history restore, split bubbles, source modal dedupe/download, escalation lock. | Add Vitest/RTL chat tests with fetch mocks and localStorage assertions. |
| Regression | Existing Dashboard, Config, Escalamiento, S3, Catálogo, Guías, Logs remain reachable. | Extend layout/nav tests and keep current slice tests passing. |

## Migration / Rollout

No data migration required. Roll out by deploying backend proxy plus admin route, then remove the `frontend` service from Compose/deployment references. Rollback restores the standalone service and removes `/admin/chat` additions.

## Open Questions

- [ ] Whether deployment IaC still references `PUBLIC_FRONTEND_URL` or a separate frontend image promotion path.
