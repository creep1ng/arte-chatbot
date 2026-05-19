export interface DashboardMetrics {
  active_sessions: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  escalation_rate: number;
  intent_distribution: Record<string, number>;
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
