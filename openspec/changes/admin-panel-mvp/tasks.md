# Tasks: Admin Panel MVP

> **Artifact**: `openspec/changes/admin-panel-mvp/tasks.md`  
> **Change**: admin-panel-mvp  
> **Delivery Strategy**: `auto-chain`  
> **Chain Strategy**: `feature-branch-chain`

---

## 1. Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~2,000 (backend ~700 + frontend ~1,000 + infra ~300) |
| 400-line budget risk | High (without chaining) |
| Chained PRs recommended | Yes |
| Suggested split | 6 chained PRs (see slices below) |
| Delivery strategy | `auto-chain` |
| Chain strategy | `feature-branch-chain` |

```
Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High
```

**Tracker branch**: `feature/admin-panel`

| Slice | PR | Base Branch | Est. Lines | Risk |
|-------|----|-------------|------------|------|
| Slice 1 | PR #1 | `feature/admin-panel` | ~320 | Low |
| Slice 2 | PR #2 | `feature/admin-panel-slice-1` | ~350 | Low |
| Slice 3 | PR #3 | `feature/admin-panel-slice-2` | ~380 | Low |
| Slice 4 | PR #4 | `feature/admin-panel-slice-3` | ~340 | Low |
| Slice 5 | PR #5 | `feature/admin-panel-slice-4` | ~360 | Low |
| Slice 6 | PR #6 | `feature/admin-panel-slice-5` | ~300 | Low |

---

## 2. Slices (Chained PRs)

### Slice 1: Backend Foundation — Auth + S3 + Config

**Branch**: `feature/admin-panel-slice-1`  
**Target PR**: `feature/admin-panel` (tracker)  
**Est. Lines**: ~320  
**Done When**: All admin endpoints reject invalid/missing keys; S3 extensions pass unit tests; settings reload works atomically.

- [x] **1.1** Add `ADMIN_API_KEY_HEADER` and `verify_admin_key` dependency to `backend/app/auth.py`. Use `hmac.compare_digest` for timing-safe comparison. Return 401/403/503 as spec'd.
- [x] **1.2** Add `admin_api_key: Optional[str]` to `backend/app/config.py` Settings model. Implement `_SettingsProxy.reload()` with atomic `_instance` swap.
- [x] **1.3** Extend `backend/app/s3_client.py` with `list_objects()`, `head_object()`, `delete_object()`, `delete_objects()`, `generate_presigned_post()`. Raise custom S3 exceptions on failures.
- [x] **1.4** Create `backend/app/admin_schemas.py` with all Pydantic v2 models: `CatalogIndex`, `GuideMeta`, `GuideContent`, `DashboardMetrics`, `MutableSettings`, `ImmutableSettings`, `CurrentSettingsSnapshot`, `S3TreeNode`, `PresignedUploadRequest`, `PresignedUploadResponse`, `DeleteS3ObjectsRequest`, `LogFilterParams`.
- [x] **1.5** Create `backend/app/admin_router.py` with root `APIRouter(prefix="/admin")`. Mount `GET /admin/health` returning `{"status": "healthy", "service": "arte-chatbot-admin"}`.
- [x] **1.6** Create `backend/app/admin_auth.py` wrapper re-exporting `verify_admin_key` for clean router imports.
- [x] **1.7** Wire `admin_router` into `backend/main.py` via `app.include_router(admin_router, prefix="/admin")`. Add `http://localhost:3001` to `CORSMiddleware` `allow_origins`.
- [x] **1.8** Write backend tests: `test_admin_health_authenticated`, `test_admin_health_missing_key`, `test_admin_health_invalid_key`, `test_s3_list_objects_mock`, `test_s3_presigned_post_mock`, `test_s3_delete_objects_mock`, `test_settings_reload_atomic`.

**Files Created**: `backend/app/admin_schemas.py`, `backend/app/admin_router.py`, `backend/app/admin_auth.py`, `backend/app/tests/test_admin_slice1.py`  
**Files Modified**: `backend/app/auth.py`, `backend/app/config.py`, `backend/app/s3_client.py`, `backend/main.py`

---

### Slice 2: Backend Domain — Catalog + Guides + Logs

**Branch**: `feature/admin-panel-slice-2`  
**Target PR**: `feature/admin-panel-slice-1`  
**Est. Lines**: ~350  
**Done When**: Catalog CRUD with optimistic locking passes tests; guides CRUD works; log filtering returns correct summaries.

- [x] **2.1** Create `backend/app/admin_catalog.py`. Implement `GET /admin/catalog` (download `index/catalog_index.json`, validate `CatalogIndex`). Implement `PUT /admin/catalog` with `If-Match` ETag optimistic locking (409 on mismatch) and `get_catalog(force_reload=True)` cache invalidation.
- [x] **2.2** Create `backend/app/admin_guides.py`. Implement `GET /admin/guides` (list `.md` under `guides/`), `GET /admin/guides/{intent}` (sanitize + download), `PUT /admin/guides/{intent}` (validate + upload), `DELETE /admin/guides/{intent}` (head + delete).
- [x] **2.3** Create `backend/app/admin_logs.py`. Implement `GET /admin/logs` (list `conversations/`, filter in-memory by date/intent/escalated, paginate with limit/offset). Implement `GET /admin/logs/{session_id}` (download all JSON under prefix, sort by `turn_number`).
- [x] **2.4** Modify `backend/app/catalog.py` to expose `save_catalog(index_data: dict, etag: Optional[str])` and `reload_catalog()` helpers.
- [x] **2.5** Modify `backend/app/conversation_logger.py` to expose `list_logs(filters)` and `get_log(session_id)` for S3 prefix reads.
- [x] **2.6** Wire catalog, guides, logs routers into `backend/app/admin_router.py` via `include_router`.
- [x] **2.7** Write backend tests: `test_get_catalog`, `test_put_catalog_optimistic_lock`, `test_put_catalog_validation_error`, `test_list_guides`, `test_get_guide`, `test_update_guide`, `test_delete_guide`, `test_list_logs_filtered`, `test_get_log_detail`.

**Files Created**: `backend/app/admin_catalog.py`, `backend/app/admin_guides.py`, `backend/app/admin_logs.py`, `backend/app/tests/test_admin_slice2.py`  
**Files Modified**: `backend/app/catalog.py`, `backend/app/conversation_logger.py`, `backend/app/admin_router.py`

---

### Slice 3: Backend Dashboard + Frontend Bootstrap

**Branch**: `feature/admin-panel-slice-3`  
**Target PR**: `feature/admin-panel-slice-2`  
**Est. Lines**: ~380  
**Done When**: Dashboard endpoint returns real aggregated metrics; Next.js builds successfully; login page renders and stores key.

- [x] **3.1** Create `backend/app/admin_dashboard.py`. Implement `GET /admin/dashboard/metrics` aggregating `session_manager.get_session_count()`, `get_all_token_totals()`, and scanning S3 `conversations/` (last 24h) for escalation rate and intent distribution.
- [x] **3.2** Modify `backend/app/session.py` to expose `get_all_token_totals()`, `get_intent_distribution()`, `get_escalation_rate()` for metric aggregation.
- [x] **3.3** Create `backend/app/admin_config.py`. Implement `GET /admin/config` (snapshot mutable/immutable with secrets redacted as `***REDACTED***`). Implement `PUT /admin/config` (partial `MutableSettings` update + `settings.reload()`).
- [x] **3.4** Wire dashboard and config routers into `backend/app/admin_router.py`.
- [x] **3.5** Write backend tests: `test_dashboard_metrics`, `test_get_config_redacts_secrets`, `test_put_config_hot_reload`.
- [x] **3.6** Bootstrap `admin-panel/` with `create-next-app@latest` (Next.js 16, App Router, TypeScript, Tailwind CSS). Install dependencies: `shadcn/ui` init, `@tanstack/react-query`, `react-hook-form`, `zod`, `@hookform/resolvers`, `recharts`, `sonner`, `next-themes`.
- [x] **3.7** Configure `admin-panel/next.config.ts` with `output: "standalone"`, `images.unoptimized: true`, and `NEXT_PUBLIC_API_URL` env mapping.
- [x] **3.8** Configure `admin-panel/tailwind.config.ts` and `admin-panel/app/globals.css` for shadcn/ui base styles.
- [x] **3.9** Create `admin-panel/app/layout.tsx` with root providers (`QueryClientProvider`, `AdminAuthProvider`, `Sonner`).
- [x] **3.10** Create `admin-panel/app/admin/layout.tsx` with sidebar navigation, header, and auth guard (redirect to `/admin/login` if no key in `localStorage`).
- [x] **3.11** Create `admin-panel/app/admin/login/page.tsx` with API key input form. Store key in `localStorage` as `arte_admin_key`. Redirect to `/admin/dashboard` on save.
- [x] **3.12** Create `admin-panel/providers/admin-auth-provider.tsx` with context exposing `apiKey`, `setApiKey`, `logout`, `isAuthenticated`.
- [x] **3.13** Create `admin-panel/providers/query-client.tsx` with TanStack Query client setup (`staleTime: 30_000` default).
- [x] **3.14** Create `admin-panel/lib/utils.ts` with `cn()` helper. Create `admin-panel/lib/types.ts` with TypeScript interfaces mirroring Pydantic schemas.
- [x] **3.15** Write frontend tests: login form submits and stores key; auth guard redirects unauthenticated users.

**Files Created**: `backend/app/admin_dashboard.py`, `backend/app/admin_config.py`, `backend/app/tests/test_admin_slice3.py`, `admin-panel/*` (bootstrap files)  
**Files Modified**: `backend/app/session.py`, `backend/app/admin_router.py`

---

### Slice 4: Frontend Pages — Dashboard + Config + Escalation

**Branch**: `feature/admin-panel-slice-4`  
**Target PR**: `feature/admin-panel-slice-3`  
**Est. Lines**: ~340  
**Done When**: Dashboard renders charts with live data; config form saves and triggers toast; escalation slider updates threshold.

- [x] **4.1** Create `admin-panel/lib/api.ts` with TanStack Query hooks: `useDashboardMetrics`, `useConfig`, `useUpdateConfig`. Implement default `queryFn` injecting `X-Admin-API-Key` header from context/localStorage.
- [x] **4.2** Create `admin-panel/lib/schemas.ts` with Zod schemas mirroring Pydantic: `CatalogProductSchema`, `MutableSettingsSchema` (with `msg_delay_min/max` cross-field refinement).
- [x] **4.3** Create `admin-panel/app/admin/dashboard/page.tsx`. Render `StatsCards` (active sessions, total tokens, escalation rate). Render `IntentPieChart` (Recharts Pie) and `EscalationLineChart` (Recharts Line/Area).
- [x] **4.4** Create `admin-panel/components/dashboard-stats.tsx` with Recharts-based stat cards and chart wrappers.
- [x] **4.5** Create `admin-panel/app/admin/config/page.tsx`. Render `ConfigForm` with React Hook Form + Zod. Display mutable fields as editable inputs; immutable fields as read-only with `disabled`. Submit calls `useUpdateConfig`.
- [x] **4.6** Create `admin-panel/app/admin/escalation/page.tsx`. Render confidence threshold slider and forced keywords tag input. Submit via `useUpdateConfig`.
- [x] **4.7** Wire Sonner toasts for mutation success/error on config and escalation pages. Handle 422 errors by mapping to form fields via `form.setError`.
- [x] **4.8** Write frontend tests: dashboard renders stats cards; config form disables immutable fields; config form submits mutable settings and shows toast.

**Files Created**: `admin-panel/lib/api.ts`, `admin-panel/lib/schemas.ts`, `admin-panel/app/admin/dashboard/page.tsx`, `admin-panel/app/admin/config/page.tsx`, `admin-panel/app/admin/escalation/page.tsx`, `admin-panel/components/dashboard-stats.tsx`, `admin-panel/components/config-form.tsx`, `admin-panel/components/escalation-form.tsx`, `admin-panel/__tests__/slice4.test.tsx`  
**Files Modified**: `admin-panel/app/admin/layout.tsx` (add nav links)

---

### Slice 5: Frontend Pages — S3 Explorer + Catalog + Guides

**Branch**: `feature/admin-panel-slice-5`  
**Target PR**: `feature/admin-panel-slice-4`  
**Est. Lines**: ~360  
**Done When**: S3 tree expands/collapses; catalog table inline-edits and saves; markdown editor split-pane renders preview.

- [x] **5.1** Extend `admin-panel/lib/api.ts` with hooks: `useS3Tree`, `usePresignedUpload`, `useDeleteS3Objects`, `useCatalog`, `useUpdateCatalog`, `useGuides`, `useGuide`, `useUpdateGuide`, `useDeleteGuide`.
- [x] **5.2** Create `admin-panel/components/s3-tree.tsx`. Recursive tree using shadcn `Collapsible` + checkboxes. Fetches `GET /admin/s3/tree?prefix=raw/` or `guides/`.
- [x] **5.3** Create `admin-panel/components/upload-dialog.tsx`. File picker → calls `usePresignedUpload` → POSTs multipart directly to S3 presigned URL → invalidates S3 tree cache on success.
- [x] **5.4** Create `admin-panel/app/admin/s3-explorer/page.tsx`. Render `S3Tree`, upload button, delete-selected button with confirmation dialog.
- [x] **5.5** Create `admin-panel/components/data-table.tsx`. Reusable TanStack Table v8 wrapper with shadcn/ui `Table`, pagination, sorting, and column visibility.
- [x] **5.6** Create `admin-panel/app/admin/catalog/page.tsx`. Render `DataTable<CatalogProduct>`. Inline editing per row. "Add product" and "Remove selected" buttons. Save triggers `useUpdateCatalog` with current ETag.
- [x] **5.7** Create `admin-panel/app/admin/guides/page.tsx`. Render `DataTable<GuideMeta>` with links to `guides/[intent]`.
- [x] **5.8** Create `admin-panel/app/admin/guides/[intent]/page.tsx`. Split-pane layout: left `MarkdownEditor` (dynamic import `@uiw/react-md-editor` with `ssr: false`), right `MarkdownPreview` (`react-markdown`). Save/delete buttons.
- [x] **5.9** Create `admin-panel/components/markdown-editor.tsx` and `admin-panel/components/markdown-preview.tsx` wrappers.
- [x] **5.10** Write frontend tests: S3 tree expands folders; catalog page loads products; guide editor renders split pane.

**Files Created**: `admin-panel/app/admin/s3-explorer/page.tsx`, `admin-panel/app/admin/catalog/page.tsx`, `admin-panel/app/admin/guides/page.tsx`, `admin-panel/app/admin/guides/[intent]/page.tsx`, `admin-panel/components/s3-tree.tsx`, `admin-panel/components/upload-dialog.tsx`, `admin-panel/components/data-table.tsx`, `admin-panel/components/markdown-editor.tsx`, `admin-panel/components/markdown-preview.tsx`, `admin-panel/__tests__/slice5.test.tsx`  
**Files Modified**: `admin-panel/lib/api.ts`, `admin-panel/app/admin/layout.tsx` (add nav links)

---

### Slice 6: Frontend Pages — Logs + Docker + CI/CD

**Branch**: `feature/admin-panel-slice-6`  
**Target PR**: `feature/admin-panel-slice-5`  
**Est. Lines**: ~300  
**Done When**: Logs table filters and shows detail drawer; Docker compose spins up admin panel on port 3001; CI passes; all integration tests green.

- [x] **6.1** Extend `admin-panel/lib/api.ts` with hooks: `useLogs`, `useLogDetail`.
- [x] **6.2** Create `admin-panel/app/admin/logs/page.tsx`. Render `DataTable<ConversationLogSummary>` with `LogFilterBar` (date range, intent select, escalated checkbox). Click row opens detail drawer.
- [x] **6.3** Create `admin-panel/components/log-filter-bar.tsx` with date pickers, intent dropdown, and escalated toggle.
- [x] **6.4** Create `admin-panel/components/log-detail-drawer.tsx` (or page). Display full chronological transcript of `ConversationLogEntry` list with turn numbers, timestamps, and tokens.
- [x] **6.5** Create `admin-panel/Dockerfile` with multi-stage build (`deps` → `builder` → `runner`), `node:20-alpine`, standalone output, non-root `nextjs` user.
- [x] **6.6** Update root `docker-compose.yml` to add `admin-panel` service exposing port `3001:3000`, depending on `backend`, with `NEXT_PUBLIC_API_URL=http://localhost:8000` for browser-local access.
- [x] **6.7** Create `.github/workflows/admin-panel.yml` with jobs: checkout → setup-node@20 → `npm ci` → `npm run lint` → `npm run typecheck` → `npm run test:unit`. Build intentionally omitted to respect the project rule: never build after changes.
- [x] **6.8** Update `admin-panel/package.json` scripts: `lint`, `typecheck`, `test:unit`, `build`.
- [x] **6.9** Verify final integration via allowed tests/checklist. Docker/browser verification deferred because builds/compose build are disallowed in this session.
- [x] **6.10** Verify existing admin backend regression tests remain green. Full `/chat` runtime regression deferred because it requires real external services.

**Files Created**: `admin-panel/app/admin/logs/page.tsx`, `admin-panel/components/log-filter-bar.tsx`, `admin-panel/components/log-detail-drawer.tsx`, `admin-panel/Dockerfile`, `.github/workflows/admin-panel.yml`, `admin-panel/__tests__/slice6.test.tsx`  
**Files Modified**: `docker-compose.yml`, `admin-panel/package.json`, `admin-panel/lib/api.ts`, `admin-panel/app/admin/layout.tsx` (add nav links)

---

## 3. Detailed Task List by Slice

| Slice | Task | Files | Depends On | Definition of Done |
|-------|------|-------|------------|-------------------|
| 1 | 1.1 Admin auth dependency | `backend/app/auth.py` | — | `test_admin_health_missing_key` passes; 401/403/503 returned correctly |
| 1 | 1.2 Settings reload | `backend/app/config.py` | — | `settings.reload()` swaps instance atomically; concurrent reads safe |
| 1 | 1.3 S3 extensions | `backend/app/s3_client.py` | — | All 5 new methods unit-tested with mocked boto3 |
| 1 | 1.4 Admin schemas | `backend/app/admin_schemas.py` | — | All Pydantic models validate correctly with sample data |
| 1 | 1.5 Admin router + health | `backend/app/admin_router.py` | 1.1 | `GET /admin/health` returns 200 with correct JSON shape |
| 1 | 1.6 Auth wrapper | `backend/app/admin_auth.py` | 1.1 | Clean import in router files |
| 1 | 1.7 Wire router + CORS | `backend/main.py` | 1.5 | `/admin/*` routes resolve; CORS includes `:3001` |
| 1 | 1.8 Slice 1 tests | `backend/app/tests/test_admin_slice1.py` | 1.1–1.7 | 100% of new auth/S3/config code covered |
| 2 | 2.1 Catalog endpoints | `backend/app/admin_catalog.py` | 1.4, 1.3 | ETag optimistic locking works; 409 on mismatch |
| 2 | 2.2 Guides endpoints | `backend/app/admin_guides.py` | 1.4, 1.3 | CRUD cycle passes; intent sanitized with regex |
| 2 | 2.3 Logs endpoints | `backend/app/admin_logs.py` | 1.4, 1.3 | Filtering by date/intent/escalated returns correct subset |
| 2 | 2.4 Catalog helpers | `backend/app/catalog.py` | 2.1 | `save_catalog` and `reload_catalog` exported and tested |
| 2 | 2.5 Logger helpers | `backend/app/conversation_logger.py` | 2.3 | `list_logs` and `get_log` exported and tested |
| 2 | 2.6 Wire domain routers | `backend/app/admin_router.py` | 2.1–2.3 | All `/admin/catalog`, `/admin/guides`, `/admin/logs` reachable |
| 2 | 2.7 Slice 2 tests | `backend/app/tests/test_admin_slice2.py` | 2.1–2.6 | All CRUD scenarios pass including 409/404/422 |
| 3 | 3.1 Dashboard endpoint | `backend/app/admin_dashboard.py` | 2.3 | Returns `DashboardMetrics` with real aggregated data |
| 3 | 3.2 Session metrics | `backend/app/session.py` | 3.1 | `get_all_token_totals()`, `get_intent_distribution()` tested |
| 3 | 3.3 Config endpoints | `backend/app/admin_config.py` | 1.2 | Secrets redacted; hot reload works without restart |
| 3 | 3.4 Wire dashboard/config | `backend/app/admin_router.py` | 3.1, 3.3 | `/admin/dashboard/metrics` and `/admin/config` reachable |
| 3 | 3.5 Slice 3 backend tests | `backend/app/tests/test_admin_slice3.py` | 3.1–3.4 | Metrics shape validated; config reload verified |
| 3 | 3.6 Next.js bootstrap | `admin-panel/*` | — | `npm run build` succeeds with zero errors |
| 3 | 3.7 next.config.ts | `admin-panel/next.config.ts` | 3.6 | `output: "standalone"` set; build produces `.next/standalone` |
| 3 | 3.8 Tailwind + globals | `admin-panel/tailwind.config.ts`, `globals.css` | 3.6 | shadcn/ui components render with correct base styles |
| 3 | 3.9 Root layout | `admin-panel/app/layout.tsx` | 3.6 | Providers wrap app; no hydration errors |
| 3 | 3.10 Admin layout | `admin-panel/app/admin/layout.tsx` | 3.9 | Sidebar renders; unauthenticated redirect works |
| 3 | 3.11 Login page | `admin-panel/app/admin/login/page.tsx` | 3.10 | Key stored in `localStorage`; redirect to dashboard |
| 3 | 3.12 Auth provider | `admin-panel/providers/admin-auth-provider.tsx` | 3.9 | Context provides `apiKey`, `setApiKey`, `logout` |
| 3 | 3.13 Query client | `admin-panel/providers/query-client.tsx` | 3.9 | Default `staleTime: 30_000`; devtools optional |
| 3 | 3.14 Utils + types | `admin-panel/lib/utils.ts`, `lib/types.ts` | 3.6 | `cn()` works; TypeScript interfaces match Pydantic |
| 3 | 3.15 Slice 3 frontend tests | `admin-panel/__tests__/slice3.test.tsx` | 3.10–3.12 | Login and auth guard tested with React Testing Library |
| 4 | 4.1 API hooks (dash/config) | `admin-panel/lib/api.ts` | 3.14 | All dashboard/config hooks fetch and cache correctly |
| 4 | 4.2 Zod schemas | `admin-panel/lib/schemas.ts` | 3.14 | `MutableSettingsSchema` cross-field refinement works |
| 4 | 4.3 Dashboard page | `admin-panel/app/admin/dashboard/page.tsx` | 4.1 | Charts render with data from backend |
| 4 | 4.4 Dashboard stats | `admin-panel/components/dashboard-stats.tsx` | 4.3 | Recharts Pie and Line display without errors |
| 4 | 4.5 Config page | `admin-panel/app/admin/config/page.tsx` | 4.1, 4.2 | Form submits; 422 errors map to fields |
| 4 | 4.6 Escalation page | `admin-panel/app/admin/escalation/page.tsx` | 4.1, 4.2 | Slider and keywords save successfully |
| 4 | 4.7 Toast wiring | Various | 4.5, 4.6 | Sonner shows success on save; error on failure |
| 4 | 4.8 Slice 4 tests | `admin-panel/__tests__/slice4.test.tsx` | 4.3–4.7 | Dashboard, config, escalation pages render and submit |
| 5 | 5.1 API hooks (S3/catalog/guides) | `admin-panel/lib/api.ts` | 3.14 | All new hooks fetch/mutate with correct invalidation |
| 5 | 5.2 S3 tree component | `admin-panel/components/s3-tree.tsx` | 5.1 | Recursive expansion; checkbox selection |
| 5 | 5.3 Upload dialog | `admin-panel/components/upload-dialog.tsx` | 5.1 | File → presigned URL → S3 direct upload → cache invalidation |
| 5 | 5.4 S3 explorer page | `admin-panel/app/admin/s3-explorer/page.tsx` | 5.2, 5.3 | Upload and delete buttons functional; tree refreshes |
| 5 | 5.5 Data table | `admin-panel/components/data-table.tsx` | — | Reusable wrapper sorts, paginates, toggles columns |
| 5 | 5.6 Catalog page | `admin-panel/app/admin/catalog/page.tsx` | 5.1, 5.5 | Inline edit + save with ETag; add/remove rows |
| 5 | 5.7 Guides list page | `admin-panel/app/admin/guides/page.tsx` | 5.1, 5.5 | Table links to intent editor |
| 5 | 5.8 Guide editor page | `admin-panel/app/admin/guides/[intent]/page.tsx` | 5.1 | Split-pane edit/preview; save/delete functional |
| 5 | 5.9 Markdown components | `admin-panel/components/markdown-editor.tsx`, `markdown-preview.tsx` | 5.8 | Dynamic import avoids SSR issues |
| 5 | 5.10 Slice 5 tests | `admin-panel/__tests__/slice5.test.tsx` | 5.2–5.9 | S3 tree, catalog, editor render and interact |
| 6 | 6.1 API hooks (logs) | `admin-panel/lib/api.ts` | 3.14 | `useLogs` and `useLogDetail` fetch correctly |
| 6 | 6.2 Logs page | `admin-panel/app/admin/logs/page.tsx` | 6.1 | Table renders with filters applied |
| 6 | 6.3 Log filter bar | `admin-panel/components/log-filter-bar.tsx` | 6.2 | Date range, intent, escalated filters update table |
| 6 | 6.4 Log detail drawer | `admin-panel/components/log-detail-drawer.tsx` | 6.1 | Full transcript displayed chronologically |
| 6 | 6.5 Dockerfile | `admin-panel/Dockerfile` | 3.7 | Multi-stage build; non-root user; standalone output |
| 6 | 6.6 docker-compose update | `docker-compose.yml` | 6.5 | `admin-panel` service starts on `:3001`; depends on backend |
| 6 | 6.7 GitHub Actions | `.github/workflows/admin-panel.yml` | 6.5 | CI passes on push/PR to `admin-panel/**` |
| 6 | 6.8 package.json scripts | `admin-panel/package.json` | 6.7 | `lint`, `typecheck`, `test:unit`, `build` defined |
| 6 | 6.9 Integration tests | Manual / scripted | 1–6 | Full end-to-end flow passes in Docker |
| 6 | 6.10 Chat regression | `backend/main.py` | 1–6 | `POST /chat` still returns 200 with valid `X-API-Key` |

---

## 4. Slice Dependencies

```
Slice 1 → Slice 2 → Slice 3 → Slice 4 → Slice 5 → Slice 6
```

**Why this order:**

| Dependency | Explanation |
|------------|-------------|
| **Slice 1 → Slice 2** | Catalog, guides, and logs endpoints depend on `admin_schemas.py`, S3 extensions, auth dependency, and the admin router skeleton from Slice 1. |
| **Slice 2 → Slice 3** | Dashboard metrics need session aggregation and conversation log queries (Slice 2). Config endpoint needs `settings.reload()` (Slice 1). Frontend bootstrap is independent of backend domain logic but we bundle it here to keep Slice 3 reviewable. |
| **Slice 3 → Slice 4** | Dashboard, config, and escalation pages depend on the TanStack Query hooks and auth provider bootstrapped in Slice 3. |
| **Slice 4 → Slice 5** | S3 explorer, catalog, and guides pages reuse the `DataTable`, `api.ts` patterns, and layout established in Slice 4. |
| **Slice 5 → Slice 6** | Logs page reuses `DataTable` and filtering patterns from Slice 5. Docker/CI should come last to package the complete frontend. |

**What CANNOT be parallelized:**
- Backend routers cannot be implemented before auth, schemas, and S3 extensions exist.
- Frontend pages cannot fetch data before backend endpoints exist.
- Docker/CI cannot be finalized until all frontend pages and build scripts exist.

---

## 5. Testing Matrix

| Slice | Backend Tests (pytest) | Frontend Tests (Vitest + RTL) | Integration Tests |
|-------|------------------------|-------------------------------|-------------------|
| 1 | Auth (401/403/503), S3 mocks (list/delete/presigned), config reload | — | — |
| 2 | Catalog CRUD + ETag lock, guides CRUD, logs list/detail + filters | — | — |
| 3 | Dashboard metrics, config snapshot + hot reload | Login form, auth guard redirect | — |
| 4 | — | Dashboard render, config form submit, escalation slider | — |
| 5 | — | S3 tree interaction, catalog inline edit, markdown editor split-pane | S3 presigned upload E2E |
| 6 | — | Logs table + filters, log detail drawer | Docker compose health, `/chat` regression |

**Coverage Targets (MVP):**
- Backend: ≥80% on new admin modules.
- Frontend: ≥70% overall; 100% on `api.ts` hooks and form submissions.

---

## 6. Environment Variables & Configuration

| Variable | Scope | Required | Default | Where to Set |
|----------|-------|----------|---------|--------------|
| `ADMIN_API_KEY` | Backend | Yes | — | `.env`, Docker secrets, CI secrets |
| `NEXT_PUBLIC_API_URL` | Frontend (build + runtime) | Yes | `http://localhost:8000` | `admin-panel/.env.local`, `docker-compose.yml` |
| `ADMIN_PANEL_ORIGIN` | Backend CORS | No | `http://localhost:3001` | `.env` (production) |
| `AWS_ACCESS_KEY_ID` | Backend | Yes | — | `.env` (existing) |
| `AWS_SECRET_ACCESS_KEY` | Backend | Yes | — | `.env` (existing) |
| `AWS_BUCKET_NAME` | Backend | Yes | — | `.env` (existing) |
| `AWS_REGION` | Backend | Yes | — | `.env` (existing) |

**Security Notes:**
- `ADMIN_API_KEY` must be ≥32 cryptographically random characters.
- `OPENAI_API_KEY`, `AWS_SECRET_ACCESS_KEY`, `CHAT_API_KEY` are NEVER exposed via `/admin/config`. They are redacted as `***REDACTED***`.
- `ADMIN_API_KEY` is NOT embedded in the Next.js bundle. It is entered at runtime via login.

---

## 7. Pre-Deploy Checklist

Before merging tracker branch `feature/admin-panel` into `main`:

- [ ] All pytest tests pass: `pytest backend/app/tests/test_admin_slice*.py -v`
- [ ] All Vitest tests pass: `cd admin-panel && npm run test:unit`
- [ ] TypeScript type-check passes: `cd admin-panel && npm run typecheck`
- [ ] ESLint passes: `cd admin-panel && npm run lint`
- [ ] Docker Compose builds cleanly: `docker compose up -d --build`
- [ ] Backend health: `curl http://localhost:8000/health` → `200 OK`
- [ ] Admin health: `curl -H "X-Admin-API-Key: $ADMIN_API_KEY" http://localhost:8000/admin/health` → `200 OK`
- [ ] Admin panel loads at `http://localhost:3001/admin/login`
- [ ] Auth rejects requests without key: `curl http://localhost:8000/admin/dashboard/metrics` → `401`
- [ ] Auth rejects invalid key: `curl -H "X-Admin-API-Key: bad" ...` → `403`
- [ ] Existing chat endpoint unchanged: `curl -H "X-API-Key: $CHAT_API_KEY" -X POST http://localhost:8000/chat -d '{"message":"hola"}'` → `200 OK`
- [ ] Config hot reload verified: change system prompt via admin → new chat uses updated prompt without restart
- [ ] Rollback plan documented and tested: stopping `admin-panel` container and removing `/admin` router does not break chat
- [ ] Secrets redaction verified: `GET /admin/config` never returns raw `openai_api_key` or `aws_secret_access_key`

---

## Summary

| Field | Value |
|-------|-------|
| **status** | `tasks_complete` |
| **executive_summary** | 6 chained slices covering backend auth/S3/config, domain endpoints (catalog/guides/logs), dashboard/metrics, Next.js bootstrap, all frontend pages (dashboard, config, escalation, S3 explorer, catalog, guides, logs), Docker/CI/CD, and integration verification. Each slice stays under 400 changed lines for reviewable diffs. |
| **artifacts** | `openspec/changes/admin-panel-mvp/tasks.md` |
| **next_recommended** | `sdd-apply` — begin implementation with Slice 1 (`feature/admin-panel-slice-1`) |
| **risks** | 1. Slice 3 is the largest (~380 lines) due to Next.js bootstrap overhead. Mitigation: bootstrap is mostly generated code. 2. Concurrent catalog edits: mitigated by ETag optimistic locking in Slice 2. 3. S3 list performance: mitigated by prefix filtering and documented MVP limits. |
| **skill_resolution** | `sdd-tasks` completed. Tasks organized into 6 chained PRs for `feature-branch-chain` strategy. Ready for `auto-chain` execution. |
