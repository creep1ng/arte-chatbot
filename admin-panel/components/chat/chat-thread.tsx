import type { AdminChatMessage, SourceDocument } from "@/lib/types";

import { ChatMessageBubble } from "./chat-message-bubble";

interface ChatThreadProps {
  messages: AdminChatMessage[];
  isSending: boolean;
  onOpenSources: (sources: SourceDocument[]) => void;
}

export function ChatThread({ messages, isSending, onOpenSources }: ChatThreadProps) {
  if (messages.length === 0) {
    return (
      <section className="chat-empty-state" aria-label="Conversación vacía">
        <p className="chat-sidebar-kicker">Workbench</p>
        <h2>Probá conversaciones B2B con fichas técnicas reales.</h2>
        <p>
          Las respuestas usan el proxy administrativo y quedan guardadas como
          historial local sin almacenar secretos del chatbot.
        </p>
      </section>
    );
  }

  return (
    <section aria-label="Historial de conversación" className="chat-thread">
      {messages.map((message) => (
        <ChatMessageBubble
          key={message.id}
          message={message}
          onOpenSources={onOpenSources}
        />
      ))}
      {isSending ? <p className="chat-typing">Generando respuesta…</p> : null}
    </section>
  );
}
