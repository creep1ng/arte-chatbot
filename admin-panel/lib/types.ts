export interface DashboardMetrics {
  active_sessions: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  escalation_rate: number;
  intent_distribution: Record<string, number>;
}

export interface ProductVariant {
  modelo: string;
  parametros_clave: Record<string, unknown>;
}

export interface CatalogProduct {
  nombre_comercial: string;
  fabricante: string;
  categoria: string;
  subcategoria?: string | null;
  descripcion?: string | null;
  ruta_s3: string;
  variantes: ProductVariant[];
  parametros_comunes: Record<string, unknown>;
}

export interface CatalogIndex {
  products: CatalogProduct[];
}

export interface GuideMeta {
  intent: string;
  title: string;
  updated_at?: string | null;
}

export interface GuideContent {
  intent: string;
  content: string;
}

export interface S3TreeNode {
  name: string;
  key: string;
  type: "folder" | "file";
  size?: number | null;
  last_modified?: string | null;
  children?: S3TreeNode[] | null;
}

export interface PresignedUploadRequest {
  key: string;
  content_type: string;
}

export interface PresignedUploadResponse {
  url: string;
  fields: Record<string, string>;
  key: string;
}

export interface PresignedDownloadRequest {
  key: string;
  disposition: "inline" | "attachment";
}

export interface PresignedDownloadResponse {
  url: string;
  key: string;
  expires_in: number;
}

export interface DeleteS3ObjectsRequest {
  keys: string[];
}

export interface MutableSettings {
  llm_model?: string | null;
  log_level?: string | null;
  escalation_confidence_threshold?: number | null;
  false_positive_limit?: number | null;
  false_negative_limit?: number | null;
  whatsapp_formatter_enabled?: boolean | null;
  split_messages_enabled?: boolean | null;
  msg_delay_min_ms?: number | null;
  msg_delay_max_ms?: number | null;
  greeting_enabled?: boolean | null;
  greeting_timezone?: string | null;
  multi_message_buffer_enabled?: boolean | null;
  buffer_window_seconds?: number | null;
  conversation_logging_enabled?: boolean | null;
  conversation_log_prefix?: string | null;
  admin_api_key?: string | null;
}

export interface ImmutableSettings {
  openai_api_key?: string | null;
  aws_access_key_id?: string | null;
  aws_secret_access_key?: string | null;
  aws_bucket_name: string;
  aws_region: string;
  chat_api_key?: string | null;
  git_commit_hash: string;
}

export interface CurrentSettingsSnapshot {
  mutable: MutableSettings;
  immutable: ImmutableSettings;
}

export interface ConversationLogSummary {
  session_id: string;
  turn_count: number;
  last_timestamp?: string | null;
  intent_types: string[];
  escalated: boolean;
}

export interface LogFilterParams {
  session_id?: string;
  intent_type?: string;
  escalated?: boolean;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export interface ConversationLogsResponse {
  items: ConversationLogSummary[];
  total: number;
}

export interface ConversationLogEntry {
  session_id: string;
  turn_number: number;
  timestamp: string;
  user_message: string;
  bot_response: string;
  intent_type: string;
  escalate: boolean;
  source_documents: string[];
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  response_time_ms: number;
  model: string;
  git_commit_hash: string;
  user_profile?: string | null;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  is_final?: boolean;
}

export interface SourceDocument {
  ruta: string;
  contenido_relevante?: string | null;
}

export interface ChatResponse {
  response: string;
  session_id: string;
  source_documents: SourceDocument[];
  messages?: string[] | null;
  delays_ms?: number[] | null;
  escalate: boolean;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
}

export interface BufferResultResponse {
  status: "pending" | "ready" | "not_found";
  session_id: string;
  result?: string | null;
}

export type AdminChatRole = "user" | "assistant";

export interface AdminChatMessage {
  id: string;
  role: AdminChatRole;
  content: string;
  sources?: SourceDocument[];
  inputTokens?: number | null;
  outputTokens?: number | null;
  totalTokens?: number | null;
  escalate?: boolean;
  createdAt?: string;
}

export interface AdminChatConversation {
  id: string;
  sessionId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: AdminChatMessage[];
}
