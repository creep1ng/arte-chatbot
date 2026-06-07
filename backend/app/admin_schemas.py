"""Pydantic v2 models for the admin panel domain.

These schemas define the request/response payloads for all /admin endpoints
and mirror the Zod schemas used by the Next.js frontend.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ProductVariant(BaseModel):
    """A single product variant with model name and key parameters."""

    modelo: str
    parametros_clave: Dict[str, Any] = Field(default_factory=dict)


class CatalogProduct(BaseModel):
    """A product entry in the catalog index."""

    nombre_comercial: str
    fabricante: str
    categoria: str
    subcategoria: Optional[str] = None
    descripcion: Optional[str] = None
    ruta_s3: str
    variantes: List[ProductVariant] = Field(default_factory=list)
    parametros_comunes: Dict[str, Any] = Field(default_factory=dict)


class CatalogIndex(BaseModel):
    """Root catalog index containing all products."""

    products: List[CatalogProduct] = Field(default_factory=list)


class GuideMeta(BaseModel):
    """Metadata for a single guide markdown file."""

    intent: str
    title: str
    updated_at: Optional[str] = None


class GuideContent(BaseModel):
    """Content payload for a guide markdown file."""

    intent: str
    content: str


class DashboardMetrics(BaseModel):
    """Aggregated metrics for the admin dashboard."""

    active_sessions: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    escalation_rate: float = Field(..., ge=0.0, le=1.0)
    intent_distribution: Dict[str, int] = Field(default_factory=dict)


class ConversationLogSummary(BaseModel):
    """Summary of a single conversation session."""

    session_id: str
    turn_count: int
    last_timestamp: Optional[str] = None
    intent_types: List[str] = Field(default_factory=list)
    escalated: bool = False


class ConversationLogEntry(BaseModel):
    """Structured log entry for a single conversation turn."""

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
    escalation_confidence_threshold: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
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
        """Ensure msg_delay_min_ms <= msg_delay_max_ms when both are set."""
        if (
            self.msg_delay_min_ms is not None
            and self.msg_delay_max_ms is not None
            and self.msg_delay_min_ms > self.msg_delay_max_ms
        ):
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
    """Combined snapshot of mutable and immutable settings."""

    mutable: MutableSettings
    immutable: ImmutableSettings


class S3TreeNode(BaseModel):
    """A node in the hierarchical S3 tree view."""

    model_config = {"populate_by_name": True}

    name: str
    key: str
    type: str  # "folder" | "file"
    size: Optional[int] = None
    last_modified: Optional[str] = None
    children: Optional[List["S3TreeNode"]] = None


class PresignedUploadRequest(BaseModel):
    """Request body for generating a presigned S3 POST URL."""

    key: str
    content_type: str = "application/pdf"


class PresignedUploadResponse(BaseModel):
    """Response containing presigned S3 POST URL and fields."""

    url: str
    fields: Dict[str, str] = Field(default_factory=dict)
    key: str


class PresignedDownloadRequest(BaseModel):
    """Request body for generating a presigned S3 read URL."""

    key: str
    disposition: Literal["inline", "attachment"] = "inline"


class PresignedDownloadResponse(BaseModel):
    """Response containing a presigned URL for reading an S3 object."""

    url: str
    key: str
    expires_in: int


class DeleteS3ObjectsRequest(BaseModel):
    """Request body for batch-deleting S3 objects."""

    keys: List[str]


class LogFilterParams(BaseModel):
    """Query parameters for filtering conversation logs."""

    session_id: Optional[str] = None
    intent_type: Optional[str] = None
    escalated: Optional[bool] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
