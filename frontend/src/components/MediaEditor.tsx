import { useEffect, useState } from "react";

import type { BlockContent } from "../api/builderApi";

interface Props {
  kind: "image" | "video";
  content: BlockContent;
  onChange: (content: BlockContent) => void;
}

/** Inline editor for an image/video block — a URL (Telegram will fetch it
 * or accept an already-known file_id) plus an optional caption, with a
 * live thumbnail so you can see what you pasted actually loads. */
export function MediaEditor({ kind, content, onChange }: Props) {
  const url = content.media_file_id ?? "";
  const [broken, setBroken] = useState(false);

  // Re-check every time the URL changes — a fixed typo should get another try.
  useEffect(() => setBroken(false), [url]);

  return (
    <div className="media-editor" onClick={(e) => e.stopPropagation()}>
      <div className="media-editor__thumb">
        {url && !broken ? (
          kind === "image" ? (
            <img src={url} alt="" onError={() => setBroken(true)} />
          ) : (
            <div className="media-editor__video-badge">
              <span aria-hidden="true">▶</span>
              <span className="media-editor__video-url">{url}</span>
            </div>
          )
        ) : url && broken ? (
          <span className="media-editor__placeholder media-editor__placeholder--error" aria-hidden="true">
            ⚠️ Не удалось загрузить — проверь ссылку
          </span>
        ) : (
          <span className="media-editor__placeholder" aria-hidden="true">
            {kind === "image" ? "🖼️" : "🎬"}
          </span>
        )}
      </div>
      <input
        className="media-editor__url"
        placeholder={kind === "image" ? "Ссылка на изображение (https://…)" : "Ссылка на видео (https://…)"}
        value={url}
        onChange={(e) => onChange({ ...content, media_file_id: e.target.value, media_type: kind === "image" ? "photo" : "video" })}
        onPointerDown={(e) => e.stopPropagation()}
      />
      <textarea
        className="chat-bubble__textarea media-editor__caption"
        placeholder="Подпись (необязательно)"
        value={content.text ?? ""}
        onChange={(e) => onChange({ ...content, text: e.target.value })}
        onPointerDown={(e) => e.stopPropagation()}
        rows={1}
      />
    </div>
  );
}
