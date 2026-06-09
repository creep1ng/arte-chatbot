import type {
  AdminChatConversation,
  AdminChatMessage,
  ChatResponse,
  SourceDocument,
} from "@/lib/types";

export const ADMIN_CHAT_HISTORY_KEY = "arte_admin_chat_history";
const MAX_CONVERSATIONS = 12;

function nowIso(): string {
  return new Date().toISOString();
}

function createId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function getSourceKey(source: SourceDocument): string {
  return source.ruta.trim();
}

export function getSourceName(source: SourceDocument): string {
  const key = getSourceKey(source);
  return key.split("/").filter(Boolean).at(-1) ?? key;
}

export function dedupeSources(sources: SourceDocument[] = []): SourceDocument[] {
  const seen = new Set<string>();
  return sources.filter((source) => {
    const key = getSourceKey(source);
    if (!key || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export function assistantPartsFromResponse(response: ChatResponse): string[] {
  const splitParts = response.messages?.filter((message) => message.trim()) ?? [];
  if (splitParts.length > 0) {
    return splitParts;
  }

  return response.response.trim() ? [response.response] : [];
}

export function readChatHistory(): AdminChatConversation[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(ADMIN_CHAT_HISTORY_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as AdminChatConversation[]) : [];
  } catch {
    return [];
  }
}

export function writeChatHistory(conversations: AdminChatConversation[]): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(
    ADMIN_CHAT_HISTORY_KEY,
    JSON.stringify(conversations.slice(0, MAX_CONVERSATIONS)),
  );
}

export function createEmptyConversation(): AdminChatConversation {
  const timestamp = nowIso();
  return {
    id: createId("conversation"),
    sessionId: createId("admin-session"),
    title: "Nueva conversación",
    createdAt: timestamp,
    updatedAt: timestamp,
    messages: [],
  };
}

export function createUserMessage(content: string): AdminChatMessage {
  return {
    id: createId("user"),
    role: "user",
    content,
    createdAt: nowIso(),
  };
}

export function createAssistantMessages(response: ChatResponse): AdminChatMessage[] {
  const sources = dedupeSources(response.source_documents);
  return assistantPartsFromResponse(response).map((content, index) => ({
    id: createId(`assistant-${index}`),
    role: "assistant",
    content,
    sources,
    inputTokens: response.input_tokens,
    outputTokens: response.output_tokens,
    totalTokens: response.total_tokens,
    escalate: response.escalate,
    createdAt: nowIso(),
  }));
}

export function upsertConversation(
  conversations: AdminChatConversation[],
  conversation: AdminChatConversation,
): AdminChatConversation[] {
  const next = [
    { ...conversation, updatedAt: nowIso() },
    ...conversations.filter((item) => item.id !== conversation.id),
  ];
  return next.slice(0, MAX_CONVERSATIONS);
}

export function titleFromPrompt(prompt: string): string {
  const normalized = prompt.trim().replace(/\s+/g, " ");
  if (!normalized) {
    return "Nueva conversación";
  }
  return normalized.length > 42 ? `${normalized.slice(0, 39)}…` : normalized;
}
