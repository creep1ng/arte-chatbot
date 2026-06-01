# Admin Panel MVP — Technical Specification

> **Artifact**: `openspec/changes/admin-panel-mvp/spec.md`  
> **Change**: admin-panel-mvp  
> **Format**: OpenSpec delta spec (single-file composite)  
> **Standard**: RFC 2119 (MUST / SHALL / SHOULD / MAY)

---

## 1. UI Libraries for Next.js 16

### 1.1 Research & Decisions

| Category | Options Evaluated | Decision | Justification |
|----------|-------------------|----------|---------------|
| **Component Base** | shadcn/ui, Radix UI direct | **shadcn/ui** | Copy-paste components built on Radix + Tailwind. Zero lock-in, full Server Component support where possible, `"use client"` auto-marked for interactive pieces. Native App Router support in Next.js 16. |
| **Data Tables** | TanStack Table v8, AG Grid | **TanStack Table v8** | Headless, fully composable with shadcn/ui `<Table>`. AG Grid is overkill for MVP (heavy bundle, licensing complexity). TanStack supports server-side pagination/sorting/filtering out of the box. |
| **Forms & Validation** | React Hook Form + Zod, Formik + Yup | **React Hook Form + Zod** | shadcn/ui Form primitive is built on this combo. Zod provides schema-first validation that maps cleanly to Pydantic v2 via similar type semantics. Minimal re-renders. |
| **S3 Tree** | Custom recursion + shadcn Collapsible, react-arborist | **Custom recursion + Collapsible** | MVP tree is read-only/browse + basic upload/delete actions. react-arborist adds 30+ KB and DnD complexity we don't need yet. A recursive component using shadcn Collapsible + Checkbox is sufficient. |
| **Markdown Editor** | @uiw/react-md-editor, react-simplemde-editor | **@uiw/react-md-editor** (preview + edit) + **react-markdown** | Split-pane editing is native in @uiw. EasyMDE (simplemde) requires `document` access and dynamic import with `ssr: false`. Both work in Next.js 16 with dynamic import; @uiw has better React 19 compatibility track record. |
| **Charts / Dashboard** | Recharts, Tremor | **Recharts** | Pure React, lightweight, covers line/bar/pie needs. Tremor (built on Recharts) is nice but adds opinionated Tailwind classes that may conflict with shadcn theming. Recharts gives full control. |
| **Fetching / State** | TanStack Query v5, SWR, Zustand | **TanStack Query v5** | First-class caching, background revalidation, devtools, and automatic loading/error states. SWR lacks some mutation helpers; Zustand/Redux are global state managers, not data-fetching layers. TanStack Query is the de-facto standard for Next.js 16. |
| **Toast / Notifications** | Sonner, react-hot-toast | **Sonner** | shadcn/ui ecosystem native (installable via `npx shadcn add sonner`). Stacks, promises, and action toasts out of the box. Better Tailwind integration than react-hot-toast. |
| **Routing / Layout** | Next.js 16 App Router, React Router | **Next.js 16 App Router** | Requirement from proposal. File-system routing, nested layouts, server components, and parallel routes for advanced admin layouts. No extra dependency. |

### 1.2 Pydantic ↔ Zod Mapping Strategy

The frontend SHALL define Zod schemas that mirror backend Pydantic v2 models. A shared naming convention MUST be enforced:

- Pydantic `CatalogProduct` → Zod `CatalogProductSchema`
- Pydantic `ConversationLogEntry` → Zod `ConversationLogEntrySchema`
- Validation errors returned as FastAPI `422` SHALL be parsed by TanStack Query `meta.errorMessage` and surfaced via Sonner toast.

---

## 2. Backend Specifications (FastAPI)

### 2.1 Shared Pydantic Models

```python
# backend/app/admin_schemas.py
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ProductVariant(BaseModel):
    modelo: str
    parametros_clave: Dict[str, Any] = Field(default_factory=dict)


class CatalogProduct(BaseModel):
    nombre_comercial: str
    fabricante: str
    categoria: str
    subcategoria: Optional[str] = None
    descripcion: Optional[str] = None
    ruta_s3: str
    variantes: List[ProductVariant] = Field(default_factory=list)
    parametros_comunes: Dict[str, Any] = Field(default_factory=dict)


class CatalogIndex(BaseModel):
    products: List[CatalogProduct] = Field(default_factory=list)


class GuideMeta(BaseModel):
    intent: str
    title: str
    updated_at: Optional[str] = None


class GuideContent(BaseModel):
    intent: str
    content: str


class DashboardMetrics(BaseModel):
    active_sessions: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    escalation_rate: float  # 0.0 - 1.0
    intent_distribution: Dict[str, int]


class ConversationLogSummary(BaseModel):
    session_id: str
    turn_count: int
    last_timestamp: Optional[str] = None
    intent_types: List[str] = Field(default_factory=list)
    escalated: bool = False


class ConversationLogEntry(BaseModel):
    # Reuses existing model; exposed here for completeness
    session_id: str
    turn_number: int
    timestamp: str
    user_message: str
    bot_response: str
    intent_type: str
    escalate: bool
    source_documents: List[str] = Field(default_factory=list)
    input_tokens: int
    output_tokens: int
    total_tokens: int
    response_time_ms: float
    model: str
    git_commit_hash: str
    user_profile: Optional[str] = None


class MutableSettings(BaseModel):
    """Fields that can be updated at runtime via settings.reload()."""

    llm_model: Optional[str] = None
    log_level: Optional[str] = None
    escalation_confidence_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    false_positive_limit: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    false_negative_limit: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    whatsapp_formatter_enabled: Optional[bool] = None
    split_messages_enabled: Optional[bool] = None
    msg_delay_min_ms: Optional[int] = Field(default=None, ge=1000, le=10000)
    msg_delay_max_ms: Optional[int] = Field(default=None, ge=1000, le=15000)
    greeting_enabled: Optional[bool] = None
    greeting_timezone: Optional[str] = None
    multi_message_buffer_enabled: Optional[bool] = None
    buffer_window_seconds: Optional[int] = Field(default=None, ge=1, le=15)
    conversation_logging_enabled: Optional[bool] = None
    conversation_log_prefix: Optional[str] = None
    admin_api_key: Optional[str] = None

    @model_validator(mode="after")
    def _validate_delays(self) -> "MutableSettings":
        if self.msg_delay_min_ms is not None and self.msg_delay_max_ms is not None:
            if self.msg_delay_min_ms > self.msg_delay_max_ms:
                raise ValueError("msg_delay_min_ms must be <= msg_delay_max_ms")
        return self


class ImmutableSettings(BaseModel):
    """Fields that require container restart to change."""

    openai_api_key: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_bucket_name: str
    aws_region: str
    chat_api_key: Optional[str] = None
    git_commit_hash: str


class CurrentSettingsSnapshot(BaseModel):
    mutable: MutableSettings
    immutable: ImmutableSettings


class S3TreeNode(BaseModel):
    name: str
    key: str
    type: str  # "folder" | "file"
    size: Optional[int] = None
    last_modified: Optional[str] = None
    children: Optional[List["S3TreeNode"]] = None


class PresignedUploadRequest(BaseModel):
    key: str  # e.g. "raw/paneles/nuevo-panel.pdf"
    content_type: str = "application/pdf"


class PresignedUploadResponse(BaseModel):
    url: str
    fields: Dict[str, str] = Field(default_factory=dict)
    key: str


class DeleteS3ObjectsRequest(BaseModel):
    keys: List[str]


class LogFilterParams(BaseModel):
    session_id: Optional[str] = None
    intent_type: Optional[str] = None
    escalated: Optional[bool] = None
    date_from: Optional[str] = None  # ISO 8601
    date_to: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
```

### 2.2 Auth Dependency

```python
# backend/app/auth.py (addition)
from fastapi import Security
from fastapi.security import APIKeyHeader

ADMIN_API_KEY_HEADER = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)


def verify_admin_key(admin_key: str = Security(ADMIN_API_KEY_HEADER)) -> str:
    """Dependency that validates the X-Admin-API-Key header."""
    if not admin_key:
        raise HTTPException(status_code=401, detail="Missing admin API key")
    valid_key = settings.admin_api_key
    if not valid_key:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY not configured")
    if not hmac.compare_digest(admin_key, valid_key):
        raise HTTPException(status_code=403, detail="Invalid admin API key")
    return admin_key
```

### 2.3 S3Client Extensions

```python
# backend/app/s3_client.py (additions)
from typing import List

class S3Client:
    # ... existing methods ...

    def list_objects(self, prefix: str = "") -> List[dict]:
        """List objects under a prefix using list_objects_v2.

        Returns a list of dicts with keys: Key, Size, LastModified.
        """
        if not self.bucket_name:
            raise S3DownloadError("S3 bucket name not configured")
        try:
            paginator = self.client.get_paginator("list_objects_v2")
            results = []
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                results.extend(page.get("Contents", []))
            return results
        except ClientError as e:
            raise S3DownloadError(f"S3 list failed: {e}") from e

    def delete_object(self, key: str) -> None:
        """Delete a single object from S3."""
        if not self.bucket_name:
            raise S3UploadError("S3 bucket name not configured")
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=key)
        except ClientError as e:
            raise S3UploadError(f"S3 delete failed: {e}") from e

    def delete_objects(self, keys: List[str]) -> None:
        """Delete multiple objects via delete_objects batch."""
        if not self.bucket_name:
            raise S3UploadError("S3 bucket name not configured")
        try:
            self.client.delete_objects(
                Bucket=self.bucket_name,
                Delete={"Objects": [{"Key": k} for k in keys], "Quiet": True},
            )
        except ClientError as e:
            raise S3UploadError(f"S3 batch delete failed: {e}") from e

    def generate_presigned_post(
        self, key: str, content_type: str = "application/pdf", expires: int = 3600
    ) -> dict:
        """Generate a presigned POST URL for direct browser upload."""
        if not self.bucket_name:
            raise S3UploadError("S3 bucket name not configured")
        try:
            return self.client.generate_presigned_post(
                Bucket=self.bucket_name,
                Key=key,
                Fields={"Content-Type": content_type},
                Conditions=[
                    {"Content-Type": content_type},
                    ["content-length-range", 1024, 104_857_600],  # 1 KB - 100 MB
                ],
                ExpiresIn=expires,
            )
        except ClientError as e:
            raise S3UploadError(f"Presigned post generation failed: {e}") from e
```

### 2.4 Endpoint Specifications

#### E1. `GET /admin/health`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request** | None |
| **Response** | `{"status": "healthy", "service": "arte-chatbot-admin"}` |
| **Errors** | 401 (missing key), 403 (invalid key), 503 (ADMIN_API_KEY not configured) |
| **Flow** | 1. Validate admin key. 2. Return static JSON health payload. |
| **S3 Ops** | None |

#### E2. `GET /admin/dashboard/metrics`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request** | None |
| **Response** | `DashboardMetrics` |
| **Errors** | 401, 403, 500 |
| **Flow** | 1. Validate admin key. 2. Query `session_manager` for active session count and token totals aggregated across all sessions. 3. Scan `conversations/` prefix in S3 (or in-memory index if maintained) to compute escalation rate and intent distribution over the last 24h. 4. Return aggregated metrics. |
| **S3 Ops** | `list_objects_v2` on `conversations/` prefix (or none if using an in-memory aggregation refreshed periodically). |

#### E3. `GET /admin/s3/tree`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request** | Query param `prefix` (str, default `""`). Optional `delimiter` (str, default `"/"`). |
| **Response** | `List[S3TreeNode]` — hierarchical tree built from S3 keys. |
| **Errors** | 401, 403, 422 (bad prefix), 500 |
| **Flow** | 1. Validate admin key. 2. Sanitize `prefix` (disallow `..` and absolute paths). 3. Call `s3_client.list_objects(prefix)`. 4. Build tree structure splitting keys by delimiter. 5. Return tree nodes. |
| **S3 Ops** | `list_objects_v2` with `Prefix` and `Delimiter`. |

#### E4. `POST /admin/s3/presigned-upload`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request Body** | `PresignedUploadRequest` |
| **Response** | `PresignedUploadResponse` |
| **Errors** | 401, 403, 422 (invalid key path), 409 (object already exists), 500 |
| **Flow** | 1. Validate admin key. 2. Validate `key` starts with allowed prefix (`raw/` or `guides/`). Reject path traversal. 3. If `key` already exists, return 409. 4. Call `s3_client.generate_presigned_post(key, content_type)`. 5. Return URL and fields. |
| **S3 Ops** | `head_object` (existence check), `generate_presigned_post`. |

#### E5. `DELETE /admin/s3/objects`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request Body** | `DeleteS3ObjectsRequest` |
| **Response** | `{"deleted": int}` |
| **Errors** | 401, 403, 422 (empty list or invalid keys), 500 |
| **Flow** | 1. Validate admin key. 2. Validate all keys start with `raw/` or `guides/` or `index/`. Reject path traversal. 3. Call `s3_client.delete_objects(keys)`. 4. Return count of deleted objects. |
| **S3 Ops** | `delete_objects` (batch). |

#### E6. `GET /admin/catalog`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request** | None |
| **Response** | `CatalogIndex` |
| **Errors** | 401, 403, 404 (index not found in S3), 500 |
| **Flow** | 1. Validate admin key. 2. Download `index/catalog_index.json` via `s3_client.download_pdf` (or a new `get_object` method). 3. Parse JSON and validate against `CatalogIndex`. 4. Return model. |
| **S3 Ops** | `get_object` on `index/catalog_index.json`. |

#### E7. `PUT /admin/catalog`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request Body** | `CatalogIndex` |
| **Response** | `CatalogIndex` (echo saved). |
| **Errors** | 401, 403, 409 (version conflict / ETag mismatch), 422 (validation error), 500 |
| **Flow** | 1. Validate admin key. 2. Validate request body against `CatalogIndex`. 3. (Optimistic locking) Fetch current object ETag from S3. If `If-Match` header provided and mismatched, return 409. 4. Serialize to JSON bytes. 5. Upload via `s3_client.put_object(key="index/catalog_index.json", data=bytes, content_type="application/json")`. 6. Invalidate in-memory catalog singleton (`get_catalog(force_reload=True)`). 7. Return saved catalog. |
| **S3 Ops** | `head_object` (for ETag), `put_object`. |

#### E8. `GET /admin/guides`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request** | None |
| **Response** | `List[GuideMeta]` |
| **Errors** | 401, 403, 500 |
| **Flow** | 1. Validate admin key. 2. List S3 prefix `guides/` to obtain all `.md` keys. 3. Extract intent from filename (`{intent}.md`). 4. Optionally fetch `head_object` for `LastModified`. 5. Return list. |
| **S3 Ops** | `list_objects_v2` on `guides/`. |

#### E9. `GET /admin/guides/{intent}`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request** | Path param `intent` (str). |
| **Response** | `GuideContent` |
| **Errors** | 401, 403, 404 (guide not found), 500 |
| **Flow** | 1. Validate admin key. 2. Sanitize `intent` (alphanumeric + hyphens/underscores). 3. Build S3 key `guides/{intent}.md`. 4. Download via `s3_client.download_pdf` (or generic get_object). 5. Decode UTF-8 and return. |
| **S3 Ops** | `get_object` on `guides/{intent}.md`. |

#### E10. `PUT /admin/guides/{intent}`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request Body** | `GuideContent` |
| **Response** | `GuideContent` (echo saved). |
| **Errors** | 401, 403, 422 (invalid intent or body), 500 |
| **Flow** | 1. Validate admin key. 2. Sanitize `intent`. 3. Validate body `content` is non-empty string. 4. Encode to UTF-8 bytes. 5. Upload via `s3_client.put_object(key="guides/{intent}.md", data=bytes, content_type="text/markdown")`. 6. Return saved content. |
| **S3 Ops** | `put_object` on `guides/{intent}.md`. |

#### E11. `DELETE /admin/guides/{intent}`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request** | Path param `intent`. |
| **Response** | `{"deleted": true}` |
| **Errors** | 401, 403, 404, 500 |
| **Flow** | 1. Validate admin key. 2. Sanitize `intent`. 3. Build key `guides/{intent}.md`. 4. Verify existence via `head_object`; if missing return 404. 5. Call `s3_client.delete_object(key)`. 6. Return confirmation. |
| **S3 Ops** | `head_object`, `delete_object`. |

#### E12. `GET /admin/config`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request** | None |
| **Response** | `CurrentSettingsSnapshot` |
| **Errors** | 401, 403, 500 |
| **Flow** | 1. Validate admin key. 2. Read current settings from `settings` proxy. 3. Split into `MutableSettings` and `ImmutableSettings` snapshots. 4. Return combined snapshot. |
| **S3 Ops** | None |

#### E13. `PUT /admin/config`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request Body** | `MutableSettings` (partial updates allowed). |
| **Response** | `CurrentSettingsSnapshot` |
| **Errors** | 401, 403, 422 (validation error), 500 |
| **Flow** | 1. Validate admin key. 2. Validate request body against `MutableSettings`. 3. Update corresponding environment variables or internal state. 4. Call `settings.reload()` to atomically swap the proxy instance. 5. Return new settings snapshot. |
| **S3 Ops** | None |

#### E14. `GET /admin/logs`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request** | Query params `LogFilterParams`. |
| **Response** | `List[ConversationLogSummary]` + `total` count. |
| **Errors** | 401, 403, 422 (bad date format), 500 |
| **Flow** | 1. Validate admin key. 2. List S3 prefix `conversations/` (paginated). 3. Filter by query params (date range, intent, escalated). 4. Aggregate per-session summaries. 5. Apply limit/offset. 6. Return summaries and total count. |
| **S3 Ops** | `list_objects_v2` on `conversations/` (potentially heavy; may require S3 Select or Athena in v2). |

#### E15. `GET /admin/logs/{session_id}`

| Attribute | Value |
|-----------|-------|
| **Auth** | `verify_admin_key` |
| **Request** | Path param `session_id`. |
| **Response** | `List[ConversationLogEntry]` (chronological). |
| **Errors** | 401, 403, 404 (session not found), 500 |
| **Flow** | 1. Validate admin key. 2. List S3 prefix `conversations/{session_id}/`. 3. Download all JSON objects under that prefix. 4. Parse into `ConversationLogEntry`. 5. Sort by `turn_number`. 6. Return list. |
| **S3 Ops** | `list_objects_v2` + `get_object` (multiple) on `conversations/{session_id}/`. |

---

## 3. Frontend Specifications (Next.js 16)

### 3.1 Directory Structure

```
admin-panel/
├── app/
│   ├── layout.tsx                 # Root layout (Providers, metadata)
│   ├── page.tsx                   # Redirect / → /admin/dashboard
│   ├── admin/
│   │   ├── layout.tsx             # Sidebar + Header + Auth guard
│   │   ├── dashboard/page.tsx     # Dashboard with stats & charts
│   │   ├── catalog/page.tsx       # Catalog CRUD table
│   │   ├── guides/page.tsx        # Guides list
│   │   ├── guides/[intent]/page.tsx  # Guide split-pane editor
│   │   ├── s3-explorer/page.tsx   # S3 tree + upload/delete
│   │   ├── config/page.tsx        # Settings editor (mutable only)
│   │   ├── escalation/page.tsx    # Thresholds & keywords
│   │   └── logs/page.tsx          # Logs table + detail drawer
│   ├── api/                       # (Optional) proxy routes if needed
│   └── globals.css
├── components/
│   ├── ui/                        # shadcn/ui components (Button, Table, Dialog, etc.)
│   ├── data-table.tsx             # Reusable TanStack Table wrapper
│   ├── s3-tree.tsx                # Recursive S3 tree browser
│   ├── markdown-editor.tsx        # Dynamic import of @uiw/react-md-editor
│   ├── markdown-preview.tsx       # react-markdown wrapper
│   └── dashboard-stats.tsx        # Recharts cards for metrics
├── lib/
│   ├── api.ts                     # TanStack Query hooks + fetch wrappers
│   ├── types.ts                   # TypeScript types mapped from Pydantic
│   └── utils.ts                   # cn() helper, formatters
├── hooks/
│   └── use-admin-auth.ts          # Auth context consumer
├── providers/
│   ├── query-client.tsx           # TanStack Query client setup
│   ├── admin-auth-provider.tsx    # Context for X-Admin-API-Key
│   └── theme-provider.tsx         # next-themes wrapper (optional)
├── public/
└── next.config.ts
```

### 3.2 Routes & Pages

| Route | Page Content | Key Components | TanStack Query Hooks |
|-------|--------------|----------------|----------------------|
| `/admin/login` | Login form (API key input). Stores key in `localStorage`. | `LoginForm` | `useLogin` (custom, sets key) |
| `/admin/dashboard` | Metrics cards, intent distribution pie chart, escalation rate line chart. | `DashboardStats`, `Recharts` components | `useDashboardMetrics` |
| `/admin/catalog` | Data table of products. Inline editing + save. Add/remove product rows. | `DataTable`, `CatalogFormDialog` | `useCatalog`, `useUpdateCatalog` |
| `/admin/guides` | Table of guides (intent, title, last modified). Links to editor. | `DataTable` | `useGuides` |
| `/admin/guides/[intent]` | Split-pane markdown editor (left: edit, right: preview). Save/Delete. | `MarkdownEditor`, `MarkdownPreview` | `useGuide`, `useUpdateGuide`, `useDeleteGuide` |
| `/admin/s3-explorer` | Tree view of `raw/` and `guides/`. Upload button (presigned), delete selected. | `S3Tree`, `UploadDialog` | `useS3Tree`, `usePresignedUpload`, `useDeleteS3Objects` |
| `/admin/config` | Form with mutable settings only. Read-only view of immutable settings. | `ConfigForm` | `useConfig`, `useUpdateConfig` |
| `/admin/escalation` | Confidence threshold slider, forced keywords tag input. | `EscalationForm` | `useConfig`, `useUpdateConfig` |
| `/admin/logs` | Table of session summaries. Filters by date/intent/escalated. | `DataTable`, `LogFilterBar` | `useLogs` |
| `/admin/logs/{session_id}` | Detail view (drawer or page) with full transcript timeline. | `LogDetailDrawer` | `useLogDetail` |

### 3.3 Authentication in Frontend

- **Storage**: `X-Admin-API-Key` SHALL be stored in `localStorage` under key `arte_admin_key`.
- **Provider**: An `AdminAuthProvider` React Context SHALL wrap the app. It provides `apiKey`, `setApiKey`, and `logout`.
- **Injection**: The TanStack Query client MUST include a default `queryFn` that reads `apiKey` from context (or `localStorage`) and injects `headers: { "X-Admin-API-Key": apiKey }` into every fetch call.
- **Guard**: `app/admin/layout.tsx` MUST check for the presence of `apiKey`. If absent, redirect to `/admin/login` via `useRouter`.
- **Logout**: Clearing `localStorage` and invalidating the QueryClient cache MUST trigger redirect to `/admin/login`.

### 3.4 Error Handling

| HTTP Status | Frontend Behavior |
|-------------|-------------------|
| **401** | Redirect immediately to `/admin/login`. Clear `localStorage` key. |
| **403** | Show Sonner toast: "Acceso denegado. Verifica tu API key." Redirect to login after 3s. |
| **404** | Show Sonner toast with specific message (e.g., "Guía no encontrada"). |
| **409** | Show Sonner toast with conflict details (e.g., "El archivo ya existe en S3"). |
| **422** | Parse field errors from FastAPI and display inline next to form fields (React Hook Form `setError`). |
| **500** | Show Sonner toast: "Error del servidor. Intenta más tarde." Log to console. |
| **Network** | TanStack Query retries 3 times with exponential backoff, then surfaces toast. |

### 3.5 Build Configuration

```typescript
// admin-panel/next.config.ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",       // Docker-friendly Node server
  // output: "export",        // Alternative: static export if no runtime server needed
  distDir: ".next",
  images: {
    unoptimized: true,        // Required for static export or simplified Docker setup
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
};

export default nextConfig;
```

> **Note**: `output: 'standalone'` is RECOMMENDED because the admin panel MAY use Next.js API routes (proxy) or server components for internal orchestration. If the panel is 100% client-side fetching the backend, `output: 'export'` is acceptable but limits dynamic behavior.

---

## 4. Docker / Infrastructure

### 4.1 `admin-panel/Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1
FROM node:20-alpine AS base

# 1. Install dependencies
FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app
COPY package.json package-lock.json* pnpm-lock.yaml* ./
RUN npm ci

# 2. Build
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# 3. Production image (standalone)
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]
```

> **Requirement**: `next.config.ts` MUST set `output: 'standalone'` for this Dockerfile to work.

### 4.2 `docker-compose.yml` Addition

```yaml
services:
  # ... existing backend service ...

  admin-panel:
    build:
      context: ./admin-panel
      dockerfile: Dockerfile
    container_name: arte-admin-panel
    ports:
      - "3001:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://backend:8000
    depends_on:
      - backend
    restart: unless-stopped
```

### 4.3 Environment Variables

| Variable | Scope | Required | Description |
|----------|-------|----------|-------------|
| `ADMIN_API_KEY` | Backend only | Yes | API key for `/admin/*` endpoints. Must be strong (≥32 chars). |
| `NEXT_PUBLIC_API_URL` | Frontend (build + runtime) | Yes | Base URL of FastAPI backend (e.g., `http://localhost:8000`). |

> **Security**: `ADMIN_API_KEY` MUST NOT be embedded in the frontend bundle. It lives only in backend env and is entered by the admin into the login page.

---

## 5. Testing Strategy

### 5.1 Backend Tests (pytest)

| Endpoint | Test Name | Mock Strategy |
|----------|-----------|---------------|
| `GET /admin/health` | `test_admin_health_authenticated` | None (static response). Assert 200 + JSON shape. |
| `GET /admin/health` | `test_admin_health_missing_key` | Assert 401. |
| `GET /admin/dashboard/metrics` | `test_dashboard_metrics` | Mock `session_manager` and S3 list. Assert metrics shape. |
| `GET /admin/s3/tree` | `test_s3_tree_listing` | Mock `boto3` via `moto`. Seed S3 objects. Assert tree structure. |
| `POST /admin/s3/presigned-upload` | `test_presigned_upload_success` | Mock `generate_presigned_post`. Assert URL returned. |
| `DELETE /admin/s3/objects` | `test_delete_s3_objects_batch` | Mock `boto3` via `moto`. Seed objects, delete, assert gone. |
| `GET /admin/catalog` | `test_get_catalog` | Mock S3 `get_object` with valid JSON. Assert `CatalogIndex` parsed. |
| `PUT /admin/catalog` | `test_put_catalog_optimistic_lock` | Mock S3 `head_object` (ETag) + `put_object`. Assert 200 and reload triggered. |
| `GET /admin/guides` | `test_list_guides` | Mock S3 list under `guides/`. Assert `List[GuideMeta]`. |
| `GET /admin/guides/{intent}` | `test_get_guide_markdown` | Mock S3 get_object with markdown bytes. Assert `GuideContent`. |
| `PUT /admin/guides/{intent}` | `test_update_guide` | Mock S3 `put_object`. Assert 200 and content echo. |
| `DELETE /admin/guides/{intent}` | `test_delete_guide` | Mock S3 `head_object` + `delete_object`. Assert 200. |
| `GET /admin/config` | `test_get_config` | Patch `settings` proxy. Assert snapshot splits mutable/immutable. |
| `PUT /admin/config` | `test_put_config_hot_reload` | Patch env + call `settings.reload()`. Assert new values returned. |
| `GET /admin/logs` | `test_list_logs_filtered` | Mock S3 list + get under `conversations/`. Assert filters applied. |
| `GET /admin/logs/{session_id}` | `test_get_log_detail` | Mock S3 objects for session. Assert sorted `List[ConversationLogEntry]`. |

**Test Setup Requirements**:
- `pytest` + `httpx` (for `TestClient`).
- `moto` for mocked S3.
- `monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")` before each test.
- Reset `settings.reset()` and `session_manager` state in fixtures.

### 5.2 Frontend Tests (Vitest + React Testing Library)

| Module | Test Name | Scope |
|--------|-----------|-------|
| `LoginForm` | `renders and submits api key` | Unit: input change + button click triggers `setApiKey`. |
| `AdminAuthProvider` | `redirects to login when api key missing` | Unit: unauthenticated render of protected layout redirects. |
| `DataTable` | `renders rows and calls pagination` | Unit: TanStack Table integration with shadcn/ui components. |
| `CatalogPage` | `loads and displays products` | Integration: MSW mocks `GET /admin/catalog`. Assert rows rendered. |
| `CatalogPage` | `saves updated catalog on click` | Integration: MSW mocks `PUT /admin/catalog`. Assert mutation called. |
| `S3Tree` | `expands folders and selects files` | Unit: click folder → children rendered; checkbox selects file. |
| `MarkdownEditor` | `renders split pane with preview` | Unit: type markdown → preview renders heading. |
| `ConfigPage` | `disables immutable fields` | Unit: immutable inputs have `disabled` attribute. |
| `ConfigPage` | `submits mutable settings` | Integration: MSW mocks `PUT /admin/config`. Assert toast success. |

**Test Stack**:
- **Runner**: Vitest (Next.js 16 native support per docs).
- **DOM**: `jsdom` + `@testing-library/react`.
- **MSW**: Mock Service Worker for API interception.
- **Coverage**: `v8` provider, threshold 70% for MVP.

---

## 6. User Flows (Gherkin)

### Feature: Admin Authentication

```gherkin
Feature: Admin Authentication
  Scenario: Login con API key válida
    Given el admin navega a /admin/login
    When ingresa una API key válida y hace clic en "Ingresar"
    Then es redirigido a /admin/dashboard
    And la API key se almacena en localStorage

  Scenario: Acceso sin autenticar
    Given el admin no ha iniciado sesión
    When intenta acceder a /admin/catalog
    Then es redirigido a /admin/login
```

### Feature: Dashboard

```gherkin
Feature: Dashboard
  Scenario: Ver métricas en tiempo real
    Given el admin ha iniciado sesión
    When accede a /admin/dashboard
    Then ve el conteo de sesiones activas, tokens totales, y tasa de escalamiento
    And el gráfico de distribución de intenciones muestra datos
```

### Feature: S3 Explorer

```gherkin
Feature: S3 Explorer
  Scenario: Navegar árbol de archivos y subir PDF
    Given el admin ha iniciado sesión
    And está en /admin/s3-explorer
    When expande la carpeta "raw/paneles"
    Then ve la lista de PDFs existentes
    When selecciona "Subir archivo", elige un PDF y confirma
    Then el archivo aparece en el árbol bajo "raw/paneles"
    And recibe una notificación de éxito

  Scenario: Eliminar objetos S3
    Given el admin ha iniciado sesión
    And ha seleccionado uno o más archivos en el árbol S3
    When hace clic en "Eliminar seleccionados" y confirma
    Then los archivos desaparecen del árbol
    And recibe una notificación de éxito
```

### Feature: Catalog Editor

```gherkin
Feature: Catalog Editor
  Scenario: Editar catálogo y guardar
    Given el admin ha iniciado sesión
    And está en /admin/catalog
    When hace clic en "Añadir producto"
    And completa los campos nombre_comercial, fabricante, categoría, ruta_s3
    And hace clic en "Guardar catálogo"
    Then el sistema persiste el nuevo catálogo en S3
    And el chatbot utiliza el catálogo actualizado dentro de 30 segundos
```

### Feature: Guides Editor

```gherkin
Feature: Guides Editor
  Scenario: Crear y editar guía markdown
    Given el admin ha iniciado sesión
    And navega a /admin/guides/nueva-intencion
    When escribe contenido markdown en el editor
    Then el panel de preview renderiza el markdown en tiempo real
    When hace clic en "Guardar guía"
    Then la guía se almacena en S3 como guides/nueva-intencion.md
```

### Feature: Config Editor

```gherkin
Feature: Config Editor
  Scenario: Cambiar system prompt y verificar aplicación
    Given el admin ha iniciado sesión
    And está en /admin/config
    When modifica el campo "System Prompt"
    And hace clic en "Guardar configuración"
    Then el backend recarga settings sin reiniciar el contenedor
    And una nueva conversación en /chat utiliza el system prompt actualizado
```

### Feature: Escalation Thresholds

```gherkin
Feature: Escalation Thresholds
  Scenario: Ajustar umbral de confianza
    Given el admin ha iniciado sesión
    And está en /admin/escalation
    When desliza el slider de "Umbral de confianza" a 0.6
    And hace clic en "Guardar"
    Then el backend actualiza escalation_confidence_threshold a 0.6
    And las próximas clasificaciones de intención respetan el nuevo umbral
```

### Feature: Conversation Logs

```gherkin
Feature: Conversation Logs
  Scenario: Revisar logs de conversación
    Given el admin ha iniciado sesión
    And está en /admin/logs
    When aplica un filtro por fecha "2026-05-01" a "2026-05-16"
    Then la tabla muestra solo sesiones dentro del rango
    When hace clic en una session_id
    Then se abre el detalle con la transcripción completa turno por turno
```

---

## 7. SDD Compliance

### Requirements Summary

| Domain | Type | Requirements | Scenarios |
|--------|------|--------------|-----------|
| admin-auth | New | 2 | 2 |
| admin-dashboard | New | 1 | 1 |
| admin-s3-explorer | New | 2 | 2 |
| admin-catalog-editor | New | 1 | 1 |
| admin-guides-editor | New | 1 | 1 |
| admin-config-editor | New | 1 | 1 |
| admin-escalation | New | 1 | 1 |
| admin-conversation-logs | New | 2 | 2 |
| **Total** | — | **11** | **11** |

### Coverage

- **Happy paths**: Covered for all 8 features.
- **Edge cases**: Covered (401/403 redirects, 409 conflicts, empty catalog, missing guides).
- **Error states**: Covered via explicit error handling tables and Gherkin preconditions.

### Risks

| Risk | Likelihood | Mitigation in Spec |
|------|------------|--------------------|
| Concurrent catalog edits corrupt JSON | Med | E7 specifies optimistic locking with ETag (`If-Match`). |
| Large PDF uploads bloat backend | Med | E4 uses presigned POST; frontend uploads directly to S3. |
| Settings reload race conditions | Low | E13 specifies atomic proxy swap via `settings.reload()`. |
| CORS between panel and backend | Low | `allow_origins` in backend CORS MUST include admin panel origin. |
| Admin key leakage | Med | Key stored only in env + localStorage (client). No cookies. |
| Next.js 16 caching stale data | Low | TanStack Query `staleTime: 0` and manual invalidation on mutations. |

### Next Recommended Phase

Ready for **sdd-design** (technical design document) followed by **sdd-tasks** (implementation task breakdown). If design already exists, proceed directly to **sdd-tasks**.

### Artifacts

- `openspec/changes/admin-panel-mvp/proposal.md` (read)
- `openspec/changes/admin-panel-mvp/spec.md` (this file)

### Skill Resolution

- **sdd-spec**: Executed. Complied with single-file artifact request despite default multi-domain structure.
- **RFC 2119**: Applied (MUST, SHALL, SHOULD, MAY) in requirements and endpoint specs.
- **Gherkin**: 11 scenarios across 8 features.
- **Pydantic v2**: All schemas use v2 patterns (`model_validator`, `Field`).
