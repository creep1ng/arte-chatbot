# Proposal: Admin Panel MVP

## Intent

Build a web-based admin panel to manage the ARTE chatbot's data and configuration without requiring direct S3 access or code changes. Currently, catalog, PDFs, settings, and conversation logs are only manageable via manual S3 edits or env vars.

## Scope

### In Scope
- Next.js frontend with admin routes (`/admin/*`) and shared layout
- Dashboard: active sessions, token totals, escalation rate, intent distribution
- S3 Explorer: browse `raw/`, upload/delete PDFs, tree view
- Catalog Editor: CRUD for `catalog_index.json` with validation
- Markdown Guides Editor: new entity, split-pane editor, linked to intents
- Config Editor: system prompt, LLM model selector, dynamic Settings reload
- Escalation Thresholds: confidence slider, forced keywords editor
- Conversation Logs: table with filters, detail view with full transcript
- Admin auth: separate `X-Admin-API-Key` header, protected admin endpoints

### Out of Scope
- Intent & sales flow builder (fase 2)
- Debug simulator (fase 2)
- Live sessions viewer (fase 2)
- Evaluation dashboard (fase 2)
- Multi-user auth / RBAC (fase 2)
- Webhooks / notifications (fase 2)

## Capabilities

### New Capabilities
- `admin-dashboard`: metrics aggregation from session manager and conversation logs
- `admin-s3-explorer`: tree listing, presigned upload/delete for `raw/` prefix
- `admin-catalog-editor`: read/write `index/catalog_index.json` with schema validation
- `admin-guides-editor`: CRUD markdown files in S3 `guides/`, intent association
- `admin-config-editor`: hot-reload system prompt, model, thresholds, feature flags
- `admin-conversation-logs`: list/filter logs, transcript detail, metadata
- `admin-auth`: separate API key middleware for admin endpoints

### Modified Capabilities
- `chat-session`: expose session metrics (counts, token totals) for dashboard
- `conversation-logging`: add list/query endpoints for log retrieval
- `catalog`: add save/reload endpoint for index mutations

## Approach

**Frontend**: Next.js 16 (App Router) in `admin-panel/`, standalone service. Consumes backend REST API. Deployed as separate container or static export.

**Backend**: Extend FastAPI with `/admin/*` routers. S3 remains the single source of truth. Admin endpoints use a new `verify_admin_key` dependency (`ADMIN_API_KEY`). Settings proxy gains a `reload()` method for hot config updates without restart.

**Data Flow**:
- Frontend → Backend → S3 (for metadata/config)
- Frontend → Backend → Presigned S3 URL (for direct PDF upload/download)

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Frontend framework | Next.js 16 | User-requested; SSR, routing, and component ecosystem out of the box |
| Admin auth | Separate API key (`ADMIN_API_KEY`) | Keeps chat and admin concerns isolated; no RBAC complexity in MVP |
| Config reload | Runtime `settings.reload()` | Avoids container restart for prompt/threshold changes |
| S3 access pattern | Backend proxy + presigned URLs | Avoids CORS and credential exposure in browser |
| Guides storage | S3 `guides/{intent}.md` | Consistent with existing S3-first architecture |

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `admin-panel/` | New | Next.js 16 application with all admin UI modules |
| `backend/main.py` | Modified | Mount admin routers behind new auth dependency |
| `backend/app/auth.py` | Modified | Add `verify_admin_key` dependency |
| `backend/app/config.py` | Modified | Add `reload()` to `_SettingsProxy`; add `admin_api_key` field |
| `backend/app/catalog.py` | Modified | Add `save_catalog()` and `reload_catalog()` helpers |
| `backend/app/s3_client.py` | Modified | Add `list_objects()`, `delete_object()`, `generate_presigned_post()` |
| `backend/app/session.py` | Modified | Expose aggregated metrics (session count, tokens, intents) |
| `backend/app/conversation_logger.py` | Modified | Add `list_logs()`, `get_log()` for querying S3 conversations prefix |
| `docker-compose.yml` | Modified | Add `admin-panel` service, expose port 3001 |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Concurrent catalog edits corrupt `catalog_index.json` | Med | Optimistic locking with ETag / versionId on S3 put |
| Large PDF uploads timeout or memory-bloat backend | Med | Use presigned POST URLs; frontend uploads directly to S3 |
| Dynamic Settings reload introduces race conditions | Low | Reload swaps proxy instance atomically; reads are unaffected |
| CORS between admin panel and backend in prod | Low | Configure `allow_origins` to include admin panel origin |
| Admin key leakage grants full control | Med | Store in env var only; rotate via deployment |

## Rollback Plan

1. Revert docker-compose to remove `admin-panel` service.
2. Revert FastAPI to remove `/admin` routers (backend chat endpoints remain untouched).
3. Delete `admin-panel/` directory.
4. Rollback `backend/app/config.py`, `auth.py`, `s3_client.py` to pre-change commits.

## Dependencies

- Node.js 20+ for Next.js build
- `ADMIN_API_KEY` env var in `.env`
- S3 bucket policy allowing delete/list operations from backend credentials

## Success Criteria

- [ ] Admin panel loads at `http://localhost:3001/admin` with navigation sidebar
- [ ] Dashboard displays real session count, token totals, and escalation rate
- [ ] Catalog CRUD persists to `index/catalog_index.json` and chatbot uses updated data within 30s
- [ ] PDF upload/delete updates `raw/` tree and reflects in catalog editor
- [ ] System prompt and model changes apply without backend restart
- [ ] Escalation thresholds and keywords editable and effective immediately
- [ ] Markdown guides CRUD works in split-pane editor and links to intents
- [ ] Conversation logs table lists transcripts with filtering by date/intent/session
- [ ] All admin endpoints reject requests without valid `X-Admin-API-Key`
- [ ] Existing `/chat` and `/health` endpoints remain unchanged and functional

## Backend Endpoints Map

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/admin/health` | Admin | Admin router health check |
| GET | `/admin/dashboard/metrics` | Admin | Sessions, tokens, escalations, intents |
| GET | `/admin/s3/tree` | Admin | List S3 objects under prefix (tree) |
| POST | `/admin/s3/presigned-upload` | Admin | Get presigned URL for PDF upload |
| DELETE | `/admin/s3/objects` | Admin | Delete S3 object(s) |
| GET | `/admin/catalog` | Admin | Fetch `catalog_index.json` |
| PUT | `/admin/catalog` | Admin | Save updated catalog index |
| GET | `/admin/guides` | Admin | List guides (intent + title) |
| GET | `/admin/guides/{intent}` | Admin | Get markdown content for intent |
| PUT | `/admin/guides/{intent}` | Admin | Save markdown guide for intent |
| DELETE | `/admin/guides/{intent}` | Admin | Delete guide |
| GET | `/admin/config` | Admin | Get current Settings snapshot |
| PUT | `/admin/config` | Admin | Update mutable settings (prompt, model, thresholds) |
| GET | `/admin/logs` | Admin | List conversation logs with filters |
| GET | `/admin/logs/{session_id}` | Admin | Get full transcript for session |
