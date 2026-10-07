import { useEffect, useRef, useState } from "react";

import { ApiError, builderApi } from "../api/builderApi";
import { useDraggablePanel } from "../hooks/useDraggablePanel";
import { useEscape } from "../hooks/useEscape";

interface Props {
  botId: string;
  botUsername: string;
  onClose: () => void;
}

/** Квадратный JPEG 640×640 из любой картинки: Telegram принимает для аватара
 * только JPG, а обрезку по центру проще сделать здесь, чем объяснять. */
async function toSquareJpeg(file: File): Promise<File> {
  const bitmap = await createImageBitmap(file);
  const side = Math.min(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 640;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Браузер не смог подготовить фото");
  ctx.drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, 640, 640);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
  if (!blob) throw new Error("Не удалось подготовить фото");
  return new File([blob], "avatar.jpg", { type: "image/jpeg" });
}

/** Имя, описание и фото бота в Telegram — без похода в @BotFather. */
export function BotProfilePanel({ botId, botUsername, onClose }: Props) {
  useEscape(onClose);
  const { panelRef, handleProps: dragProps } = useDraggablePanel();
  const [name, setName] = useState("");
  const [short, setShort] = useState("");
  const [description, setDescription] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoNote, setPhotoNote] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const profile = await builderApi.getBotProfile(botId);
        setName(profile.name);
        setShort(profile.short_description);
        setDescription(profile.description);
        setLoaded(true);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Не удалось загрузить оформление");
      }
    })();
  }, [botId]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await builderApi.saveBotProfile(botId, { name, short_description: short, description });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  }

  async function onPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setPhotoBusy(true);
    setPhotoNote(null);
    setError(null);
    try {
      await builderApi.uploadBotPhoto(botId, await toSquareJpeg(file));
      setPhotoNote("Фото обновлено. Telegram покажет его в течение минуты.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить фото");
    } finally {
      setPhotoBusy(false);
    }
  }

  return (
    <>
      <div className="sheet-backdrop edit-panel-backdrop" onClick={onClose} />
      <div className="edit-panel" ref={panelRef}>
        <div
          className="edit-panel__header"
          title="Потяни, чтобы переместить окно (двойной щелчок — вернуть на место)"
          {...dragProps}
        >
          <span className="edit-panel__icon block-card__icon--welcome" aria-hidden="true">
            🎨
          </span>
          <span className="edit-panel__title">Оформление @{botUsername}</span>
          <button type="button" className="edit-panel__close" aria-label="Закрыть" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="edit-panel__body">
          {!loaded && !error && <p className="app-hint">Загружаем…</p>}
          {loaded && (
            <>
              <p className="payment-settings__lead">
                Так бот выглядит в Telegram. Менять можно здесь — в @BotFather ходить не нужно.
              </p>

              <p className="edit-panel__section-label">Фото бота</p>
              <input ref={fileRef} type="file" accept="image/*" hidden onChange={onPhoto} />
              <div className="publish-form__actions">
                <button type="button" onClick={() => fileRef.current?.click()} disabled={photoBusy}>
                  {photoBusy ? "Загружаем…" : "📤 Загрузить фото"}
                </button>
                <button
                  type="button"
                  disabled={photoBusy}
                  onClick={async () => {
                    try {
                      await builderApi.removeBotPhoto(botId);
                      setPhotoNote("Фото убрано.");
                    } catch (err) {
                      setError(err instanceof ApiError ? err.message : "Не удалось убрать фото");
                    }
                  }}
                >
                  Убрать
                </button>
              </div>
              {photoNote && <p className="app-hint">{photoNote}</p>}

              <label className="buttons-editor__field">
                <span className="buttons-editor__field-label">Имя бота ({name.length}/64)</span>
                <input
                  className="payment-editor__input"
                  maxLength={64}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>

              <label className="buttons-editor__field">
                <span className="buttons-editor__field-label">
                  «Что умеет этот бот» — видят до нажатия /start ({description.length}/512)
                </span>
                <textarea
                  className="chat-bubble__textarea edit-panel__textarea"
                  maxLength={512}
                  rows={5}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </label>

              <label className="buttons-editor__field">
                <span className="buttons-editor__field-label">
                  Коротко о боте — в профиле и при пересылке ({short.length}/120)
                </span>
                <textarea
                  className="chat-bubble__textarea edit-panel__textarea"
                  maxLength={120}
                  rows={2}
                  value={short}
                  onChange={(e) => setShort(e.target.value)}
                />
              </label>

              {error && <p className="publish-form__error">{error}</p>}
              <button type="button" className="payment-settings__save" onClick={save} disabled={saving}>
                {saving ? "Сохраняем…" : saved ? "✓ Сохранено" : "Сохранить"}
              </button>
            </>
          )}
          {error && !loaded && <p className="publish-form__error">{error}</p>}
        </div>
      </div>
    </>
  );
}
