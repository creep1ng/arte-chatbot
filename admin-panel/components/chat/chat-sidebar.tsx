import type { AdminChatConversation } from "@/lib/types";

interface ChatSidebarProps {
  conversations: AdminChatConversation[];
  selectedId: string;
  onSelect: (conversation: AdminChatConversation) => void;
}

export function ChatSidebar({
  conversations,
  selectedId,
  onSelect,
}: ChatSidebarProps) {
  return (
    <aside className="chat-sidebar">
      <section aria-labelledby="recent-chat-heading" className="chat-recent-section">
        <p id="recent-chat-heading" className="chat-sidebar-kicker">
          Recientes
        </p>
        {conversations.length === 0 ? (
          <p className="chat-empty-note">Todavía no hay conversaciones guardadas.</p>
        ) : (
          <div className="chat-recent-list">
            {conversations.map((conversation) => (
              <button
                key={conversation.id}
                type="button"
                className={
                  conversation.id === selectedId
                    ? "chat-recent-item chat-recent-item-active"
                    : "chat-recent-item"
                }
                onClick={() => onSelect(conversation)}
              >
                <span>{conversation.title}</span>
                <small>{conversation.messages.length} mensajes</small>
              </button>
            ))}
          </div>
        )}
      </section>
    </aside>
  );
}
