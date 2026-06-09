import { type FormEvent, useState } from "react";

interface ChatComposerProps {
  isSending: boolean;
  onSend: (message: string) => void;
}

export function ChatComposer({ isSending, onSend }: ChatComposerProps) {
  const [message, setMessage] = useState("");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = message.trim();
    if (!trimmed || isSending) {
      return;
    }
    onSend(trimmed);
    setMessage("");
  };

  return (
    <form className="chat-composer" onSubmit={handleSubmit}>
      <label className="sr-only" htmlFor="admin-chat-message">
        Mensaje para probar el chatbot
      </label>
      <textarea
        id="admin-chat-message"
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        placeholder="Escribí una consulta técnica para simular una conversación…"
        rows={2}
      />
      <button disabled={isSending || !message.trim()} type="submit">
        Enviar mensaje
      </button>
    </form>
  );
}
