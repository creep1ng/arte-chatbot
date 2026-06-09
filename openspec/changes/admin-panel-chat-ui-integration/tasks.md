# Tasks: Admin Panel Chat UI Integration

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 900-1,400 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 backend proxy → PR 2 admin chat UI → PR 3 runtime/CD cleanup |
| Delivery strategy | ask-always |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Secure admin chat proxy | PR 1 | Base target: `feature/admin-panel` (tracker PR #207). `backend/app/admin_chat.py`, router/main helpers, backend tests included. |
| 2 | Authenticated admin workbench | PR 2 | Base target: PR 1 branch. `admin-panel/app/admin/chat/page.tsx`, `components/chat/*`, lib/CSS/tests; depends on PR 1. |
| 3 | Retire standalone UI runtime | PR 3 | Base target: PR 2 branch. `docker-compose.yml`, `.github/workflows/*`, `infra/terraform/**/*`; depends on PR 2. |

## Phase 1: Backend Proxy (RED/GREEN)

- [x] 1.1 RED: Add `backend/app/tests/test_admin_chat.py` for admin auth, no `CHAT_API_KEY`, split fields, buffer contract.
- [x] 1.2 GREEN: Create `backend/app/admin_chat.py` with `/admin/chat` and `/admin/chat/buffer-result/{session_id}` using `verify_admin_key`.
- [x] 1.3 GREEN: Modify `backend/app/admin_router.py` and `backend/main.py` only as needed to reuse current chat/buffer processing unchanged.

## Phase 2: Admin Workbench UI (RED/GREEN)

- [x] 2.1 RED: Add `admin-panel/__tests__/admin-chat.test.tsx` for route auth, history restore, split bubbles, source modal, no stored chat key.
- [x] 2.2 GREEN: Extend `admin-panel/lib/types.ts` and `admin-panel/lib/api.ts` with chat, buffer, source, and history contracts via `adminFetch`.
- [x] 2.3 GREEN: Create `admin-panel/app/admin/chat/page.tsx` and `admin-panel/components/chat/*` for sidebar, thread, composer, bubbles, badges, and sources modal.
- [x] 2.4 GREEN: Modify `admin-panel/app/admin/layout.tsx` to add Chat navigation while preserving Dashboard, Config, Escalation, S3, Catalog, Guides, Logs.
- [x] 2.5 GREEN: Add route-scoped palette tokens in `admin-panel/app/globals.css` using `#0F0F0F`, `#FFC200`, `#736F72`, `#D8DDDE`, `#09BC8A`.

## Phase 3: Runtime and Promotion Cleanup

- [x] 3.1 RED: Add/extend deployment tests or checks proving admin origin only and no standalone Chat UI promotion/service.
- [x] 3.2 GREEN: Update `docker-compose.yml` to disable/remove standalone `frontend` as a browser access path.
- [x] 3.3 GREEN: Update `.github/workflows/ci.yml`, `.github/workflows/admin-panel.yml`, and `infra/terraform/**/*` references so backend/admin-panel are deployable and standalone Chat UI is not.

## Phase 4: Verification

- [x] 4.1 Run backend pytest for admin chat plus existing admin S3/catalog/log routes.
- [x] 4.2 Run admin-panel Vitest/RTL tests for chat behavior and existing route reachability.
- [x] 4.3 Verify OpenSpec scenarios: authenticated access, secure requests, layout, theme, split messages, datasheet modal, CORS/runtime, ECR promotion.
