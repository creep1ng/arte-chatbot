"use client";

import { useEffect, useMemo, useState } from "react";

import { ChatComposer } from "@/components/chat/chat-composer";
import {
  createAssistantMessages,
  createEmptyConversation,
  createUserMessage,
  readChatHistory,
  titleFromPrompt,
  upsertConversation,
  writeChatHistory,
} from "@/components/chat/chat-history";
import { ChatSidebar } from "@/components/chat/chat-sidebar";
import { ChatThread } from "@/components/chat/chat-thread";
import { SourceModal } from "@/components/chat/source-modal";
import { useSendAdminChatMessage } from "@/lib/api";
import type { AdminChatConversation, SourceDocument } from "@/lib/types";

export default function AdminChatPage() {
  const [conversations, setConversations] = useState<AdminChatConversation[]>([]);
  const [activeConversation, setActiveConversation] = useState<AdminChatConversation>(() =>
    createEmptyConversation(),
  );
  const [modalSources, setModalSources] = useState<SourceDocument[] | null>(null);
  const sendMessage = useSendAdminChatMessage();

  useEffect(() => {
    const stored = readChatHistory();
    setConversations(stored);
  }, []);

  const persistedConversations = useMemo(
    () => upsertConversation(conversations, activeConversation),
    [activeConversation, conversations],
  );

  const persistConversation = (conversation: AdminChatConversation) => {
    const next = upsertConversation(conversations, conversation);
    setConversations(next);
    writeChatHistory(next);
  };

  const startNewConversation = () => {
    setActiveConversation(createEmptyConversation());
  };

  const selectConversation = (conversation: AdminChatConversation) => {
    setActiveConversation(conversation);
  };

  const handleSend = async (message: string) => {
    const userMessage = createUserMessage(message);
    const title = activeConversation.messages.length
      ? activeConversation.title
      : titleFromPrompt(message);
    const optimisticConversation = {
      ...activeConversation,
      title,
      messages: [...activeConversation.messages, userMessage],
    };
    setActiveConversation(optimisticConversation);

    const response = await sendMessage.mutateAsync({
      message,
      session_id: activeConversation.sessionId,
      is_final: true,
    });
    const assistantMessages = createAssistantMessages(response);
    const nextConversation = {
      ...optimisticConversation,
      sessionId: response.session_id,
      messages: [...optimisticConversation.messages, ...assistantMessages],
    };
    setActiveConversation(nextConversation);
    persistConversation(nextConversation);
  };

  return (
    <div className="admin-chat-shell">
      <section className="chat-main-panel">
        <header className="chat-hero">
          <div>
            <p className="chat-sidebar-kicker">Arte Chatbot</p>
            <h1>Chat UI de pruebas</h1>
            <p>
              Consola administrativa para probar respuestas, revisar fuentes y validar
              conversaciones sin exponer credenciales del endpoint público.
            </p>
          </div>
          <button className="chat-new-button" type="button" onClick={startNewConversation}>
            Nueva conversación
          </button>
        </header>
        <div className="chat-workspace">
          <ChatSidebar
            conversations={persistedConversations}
            selectedId={activeConversation.id}
            onSelect={selectConversation}
          />
          <div className="chat-conversation-panel">
            <ChatThread
              messages={activeConversation.messages}
              isSending={sendMessage.isPending}
              onOpenSources={setModalSources}
            />
            <ChatComposer isSending={sendMessage.isPending} onSend={handleSend} />
          </div>
        </div>
      </section>
      {modalSources ? (
        <SourceModal sources={modalSources} onClose={() => setModalSources(null)} />
      ) : null}
    </div>
  );
}
