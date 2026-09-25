import { useEffect, useRef, useState } from "react";

import type { BlockContent } from "../api/builderApi";
import { ApiError, builderApi } from "../api/builderApi";

interface Props {
  /** "file" — для блока «Выдача»: методичка, архив, аудио. Лендинг обещает
   * «файл, ссылка или доступ», плейсхолдер блока зовёт «пришли сюда ссылку
   * или файл», а загрузить файл было негде — обложку можно, а товар,
   * который человек продаёт, нет. */
  kind: "image" | "video" | "file";
  botId: string;
  content: BlockContent;
  onChange: (content: BlockContent) => void;
}

/** Inline editor for an image/video block. Two ways to fill `media_file_id`:
 * upload the file directly (goes to this server — see app/routers/media.py,
 * capped at Settings.media_max_upload_mb) or paste a URL, meant for files
 * too big for a direct upload to make sense (Telegram will fetch those
 * itself). Either way the field ends up holding a URL bot_dispatcher hands
 * straight to aiogram — a live thumbnail shows whichever one is set. */
const ACCEPT: Record<Props["kind"], string> = {
  image: "image/*",
  video: "video/*",
  // Ровно то, что принимает сервер (app/routers/media.py) — иначе человек
  // выберет .docx и узнает об отказе только после загрузки.
  file: ".pdf,.zip,.epub,.mp3,.m4a,.ogg,application/pdf,application/zip,application/epub+zip,audio/*",
};
const NOUN: Record<Props["kind"], string> = { image: "фото", video: "видео", file: "файл" };
const PLACEHOLDER_URL: Record<Props["kind"], string> = {
  image: "Ссылка на изображение (https://…)",
  video: "Ссылка на видео (https://…)",
  file: "Ссылка на файл (https://…)",
};
const URL_MEDIA_TYPE: Record<Props["kind"], string> = {
  image: "photo",
  video: "video",
  file: "document",
};

export function MediaEditor({ kind, botId, content, onChange }: Props) {
  const url = content.media_file_id ?? "";
  const [broken, setBroken] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Re-check every time the URL changes — a fixed typo should get another try.
  useEffect(() => setBroken(false), [url]);

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // lets picking the exact same file again re-fire onChange
    if (!file) return;

    setUploading(true);
    setUploadError(null);
    try {
      const { url: uploadedUrl, media_type } = await builderApi.uploadMedia(botId, file);
      onChange({ ...content, media_file_id: uploadedUrl, media_type });
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Не удалось загрузить файл");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="media-editor" onClick={(e) => e.stopPropagation()}>
      <div className="media-editor__thumb">
        {uploading ? (
          <span className="media-editor__placeholder" aria-hidden="true">
            ⏳
          </span>
        ) : url && !broken ? (
          kind === "file" ? (
            <div className="media-editor__video-badge">
              <span aria-hidden="true">📎</span>
              <span className="media-editor__video-url">{url.split("/").pop()}</span>
            </div>
          ) : kind === "image" ? (
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
            {kind === "image" ? "🖼️" : kind === "video" ? "🎬" : "📎"}
          </span>
        )}
      </div>

      <div className="media-editor__upload-row">
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPT[kind]}
          className="media-editor__file-input"
          onChange={handleFileSelected}
          onPointerDown={(e) => e.stopPropagation()}
        />
        <button
          type="button"
          className="media-editor__upload-button"
          disabled={uploading}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploading ? "Загружаем…" : `📤 Загрузить ${NOUN[kind]}`}
        </button>
      </div>
      {uploadError && <p className="media-editor__upload-error">{uploadError}</p>}

      <p className="media-editor__or">или для тяжёлых файлов — вставь ссылку:</p>
      <input
        className="media-editor__url"
        placeholder={PLACEHOLDER_URL[kind]}
        value={url}
        onChange={(e) =>
          onChange({ ...content, media_file_id: e.target.value, media_type: URL_MEDIA_TYPE[kind] })
        }
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
