import { usePresignedDownload } from "@/lib/api";
import type { SourceDocument } from "@/lib/types";

import { getSourceKey, getSourceName } from "./chat-history";

interface SourceModalProps {
  sources: SourceDocument[];
  onClose: () => void;
}

export function SourceModal({ sources, onClose }: SourceModalProps) {
  const presignedDownload = usePresignedDownload();

  const openSource = async (source: SourceDocument) => {
    const result = await presignedDownload.mutateAsync({
      key: getSourceKey(source),
      disposition: "inline",
    });
    window.open(result.url, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="chat-modal-backdrop" role="presentation">
      <section
        aria-label="Fichas técnicas usadas"
        aria-modal="true"
        className="chat-modal"
        role="dialog"
      >
        <div className="chat-modal-header">
          <div>
            <p className="chat-sidebar-kicker">Fuentes</p>
            <h2>Fichas técnicas usadas</h2>
          </div>
          <button className="chat-modal-close" type="button" onClick={onClose}>
            Cerrar
          </button>
        </div>
        <div className="chat-source-list">
          {sources.map((source) => {
            const name = getSourceName(source);
            return (
              <article className="chat-source-card" key={getSourceKey(source)}>
                <div>
                  <h3>{name}</h3>
                  <p>{getSourceKey(source)}</p>
                  {source.contenido_relevante ? (
                    <small>{source.contenido_relevante}</small>
                  ) : null}
                </div>
                <button type="button" onClick={() => openSource(source)}>
                  Abrir {name}
                </button>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
