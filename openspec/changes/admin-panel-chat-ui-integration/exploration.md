## Exploration: Move standalone Chat UI into the admin panel

### Current State
The test Chat UI currently lives as a standalone static app in `frontend/`, served by an Nginx container on port `3000`. It stores the `CHAT_API_KEY` in `sessionStorage`, calls `POST /chat` with `X-API-Key`, keeps only the active session in memory, ignores `ChatResponse.messages`, and renders `ChatResponse.response` as a single bot bubble.

The admin panel is a Next.js 16 app in `admin-panel/`, served separately on local port `3001`, authenticated with `ADMIN_API_KEY` stored in `localStorage`, and protected by `app/admin/layout.tsx`. Existing admin features are Dashboard, Config, Escalamiento, S3 Explorer, Catálogo, Guías, Logs, and Login. These must remain intact; the safe integration point is a new authenticated route such as `/admin/chat` plus a new sidebar item, not a rewrite of existing routes.

Backend support already exists for the requested chat metadata:

- `POST /chat` returns `source_documents: [{ ruta, contenido_relevante }]`, `num_sources`, `messages`, `delays_ms`, token counts, intent metadata, escalation metadata, and `session_id`.
- `source_documents` is populated when `leer_ficha_tecnica` is used; multiple tool calls can produce multiple paths.
- `SPLIT_MESSAGES_ENABLED` causes the backend to populate `messages` and `delays_ms` when the response is split on `---`; the current static UI does not use those fields.
- Admin already has `POST /admin/s3/presigned-download`, so a Chat UI inside the admin panel can show source datasheets and open/download them using the admin key.

### Affected Areas
- `frontend/index.html` — source behavior to port: API key modal, session id handling, polling `/buffer-result/{session_id}`, escalation locking, token badge, typing state.
- `frontend/Dockerfile`, `frontend/nginx.conf`, `frontend/entrypoint.sh` — standalone service packaging that should no longer be the access path once the admin route exists.
- `docker-compose.yml` — currently exposes both `frontend` and `admin-panel`; removing the standalone Chat UI access means dropping or disabling the `frontend` service and ensuring admin remains exposed.
- `admin-panel/app/admin/layout.tsx` — add `/admin/chat` navigation without removing current admin items.
- `admin-panel/lib/api.ts` — existing `adminFetch` only sends `X-Admin-API-Key`; chat calls need either a dedicated chat client or an admin-authenticated backend proxy.
- `admin-panel/lib/types.ts` — add `ChatRequest`, `ChatResponse`, `SourceDocument`, and buffer result types mirroring backend response shapes.
- `admin-panel/components/*` or new chat feature folder — likely home for conversation list, chat thread, datasheet modal, and message bubble components.
- `backend/main.py` — `/chat` already has the needed response fields, but it requires `CHAT_API_KEY`; direct browser use from admin would either require a separate chat key prompt or a safer admin proxy.
- `backend/app/admin_s3.py` — existing presigned download endpoint can power the datasheet modal.
- `admin-panel/__tests__/*.test.tsx` — add React Testing Library coverage for the new route while preserving existing slice tests.
- `backend/tests/test_chat.py` — already covers `source_documents`; add/extend split-message response tests if backend contract needs to be locked before frontend work.

### Approaches
1. **Client-only port with separate CHAT_API_KEY prompt** — Rebuild the static UI as React components under `/admin/chat`, still calling `/chat` directly with `X-API-Key` from a Chat API key stored in browser storage.
   - Pros: Lowest backend impact; closest to current static behavior.
   - Cons: Admin users still need a second secret; leaks/stores the chat key in the browser; weakens the goal that admin is the single controlled access path.
   - Effort: Medium

2. **Admin-authenticated chat proxy** — Add admin-protected backend endpoints, for example `POST /admin/chat` and `GET /admin/chat/buffer-result/{session_id}`, that validate `X-Admin-API-Key` and internally call existing chat processing without exposing `CHAT_API_KEY` to the browser.
   - Pros: Best match for “only access through admin panel”; uses one admin credential; keeps Chat UI access governed by admin auth; unlocks presigned datasheet modal with the same key.
   - Cons: Requires backend route work and careful reuse of existing `/chat` logic to avoid behavior drift.
   - Effort: Medium

3. **Server-persisted chat history via conversation logs** — Build `/admin/chat` history from existing S3 conversation logs and `GET /admin/logs/{session_id}`.
   - Pros: Reuses persistent admin audit data; history survives devices and browser clearing when logging is enabled.
   - Cons: Conversation logging is configurable and async; logs are redacted; not ideal for immediate in-progress Chat UI state; S3 list/read latency can make the Chat UI feel heavy.
   - Effort: Medium-High

4. **Browser-persisted chat workbench history** — Persist Chat UI sessions, messages, metadata, `source_documents`, `messages`, `delays_ms`, and token totals in `localStorage` under an admin-scoped key.
   - Pros: Immediate UX, simple restore across reloads, independent of S3 logging, matches the “frontend de pruebas” nature.
   - Cons: Per-browser only; storage can be cleared; must avoid persisting secrets and cap history size.
   - Effort: Medium

### Recommendation
Use **Approach 2 + Approach 4**: implement `/admin/chat` in Next.js with browser-local conversation history, and route chat requests through admin-authenticated backend proxy endpoints. This preserves all current admin functionality, removes the standalone frontend as an access path, avoids exposing `CHAT_API_KEY` to the browser, and still uses existing backend behavior for source documents, buffering, splitting, escalation, and token accounting.

For the datasheet modal, render `Ver fichas técnicas` only when `source_documents.length > 0`; dedupe by `ruta`; show filename/path and use existing `POST /admin/s3/presigned-download` for “Ver” or “Descargar”. `contenido_relevante` is currently optional and usually null, so do not design the modal as if extracted snippets are guaranteed.

For split responses, render `data.messages` as individual bot bubbles when non-empty and fall back to `[data.response]`. If UX should simulate WhatsApp timing, apply `delays_ms` between bubbles; otherwise render immediately but preserve visual separation. The same parsing must be used for immediate `/chat` responses and parsed `/buffer-result` responses.

### Risks
- Current local CORS defaults and `.env.example` include `localhost:3000`/`5173` but not the compose admin origin `localhost:3001`; direct browser calls from admin may fail unless CORS is updated or proxied server-side.
- A direct client-only port would keep requiring `CHAT_API_KEY` in browser storage, which conflicts with admin-only access control.
- Conversation history via existing S3 logs is not a complete Chat UI persistence mechanism because logging can be disabled and writes are async.
- Removing the `frontend` service changes local operator habits and any deployment/runtime references to `PUBLIC_FRONTEND_URL`.
- `source_documents` currently exposes paths, not friendly names or guaranteed snippets; richer modal content would need catalog lookup or backend enrichment.
- Split messages are only useful if the frontend explicitly renders `messages`; rendering only `response` keeps the current bug where split responses appear as one joined bubble.

### Ready for Proposal
Yes. The proposal should scope a new authenticated `/admin/chat` workbench, an admin chat proxy or equivalent secure access mechanism, local conversation history, datasheet modal using existing source document metadata and presigned S3 URLs, split-message rendering, removal of the standalone frontend service from local/deployment access, and regression tests ensuring all current admin routes remain available.
