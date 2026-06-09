import type { AdminChatMessage, SourceDocument } from "@/lib/types";

interface ChatMessageBubbleProps {
  message: AdminChatMessage;
  onOpenSources: (sources: SourceDocument[]) => void;
}

export function ChatMessageBubble({ message, onOpenSources }: ChatMessageBubbleProps) {
  const sources = message.sources ?? [];
  const hasSources = message.role === "assistant" && sources.length > 0;
  const hasTokenMetrics =
    message.role === "assistant" &&
    (message.inputTokens != null ||
      message.outputTokens != null ||
      message.totalTokens != null);

  return (
    <article
      className={message.role === "user" ? "chat-message chat-message-user" : "chat-message"}
    >
      <div className="chat-message-card">
        <p>{message.content}</p>
        {hasTokenMetrics ? (
          <div className="chat-badge-row" aria-label="Métricas de tokens">
            {message.inputTokens != null ? <span>Entrada: {message.inputTokens}</span> : null}
            {message.outputTokens != null ? <span>Salida: {message.outputTokens}</span> : null}
            {message.totalTokens != null ? <span>Total: {message.totalTokens}</span> : null}
            {message.escalate ? <span className="chat-badge-alert">Escalar</span> : null}
          </div>
        ) : null}
      </div>
      {hasSources ? (
        <button
          className="chat-sources-button"
          type="button"
          onClick={() => onOpenSources(sources)}
        >
          Ver fichas técnicas
        </button>
      ) : null}
    </article>
  );
}
