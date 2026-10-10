"""Direct media uploads for image/video blocks.

The alternative to this — pasting a URL — has always worked (bot_dispatcher
just hands `media_file_id` straight to aiogram's send_photo/send_video,
which accepts a file_id *or* a URL Telegram fetches itself). This endpoint
gives the same field a second way to get filled in: save the bytes here,
on this server, and hand back a URL pointing at them — from the dispatcher's
side nothing changes, it's just a URL that happens to be ours instead of
someone else's CDN.

Deliberately capped (see Settings.media_max_upload_mb) — a big file should
still go through the "paste a link" path (e.g. Telegram's own CDN, or any
file host) rather than round-tripping through this server's disk.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.config import get_settings
from app.deps import get_owned_bot
from app.models.bot import Bot

router = APIRouter(prefix="/api/bots/{bot_id}/media", tags=["media"])

# Content-Type -> (extension, our media_type, magic-byte sniffer). The
# sniffer is a light defense against a mislabeled Content-Type header
# (client-supplied, trivially spoofable) — not a full format validator,
# just enough to catch "renamed .exe to .jpg" casually. Video containers
# aren't sniffed (too many valid variants for a quick check) — they're
# bounded by the same size cap and auth as everything else here.
_IMAGE_MAGIC: dict[str, bytes] = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/gif": b"GIF8",
}
#: WebP is a RIFF container: "RIFF", four bytes of length, then "WEBP". Left
#: unsniffed, it was the one image type that accepted arbitrary bytes — and
#: these files are served from the app's own origin.
_RIFF_MAGIC: dict[str, tuple[bytes, bytes]] = {
    "image/webp": (b"RIFF", b"WEBP"),
}
#: Documents are sniffed too. Every declared type gets an entry — the two
#: that did not (`application/epub+zip` and `application/x-zip-compressed`)
#: happily accepted an ELF binary or a page of HTML, which made this a free
#: file host on our own domain for anything at all.
_DOC_MAGIC: dict[str, bytes] = {
    "application/pdf": b"%PDF-",
    # Every zip-family container, .epub and modern Office files included.
    "application/zip": b"PK\x03\x04",
    "application/epub+zip": b"PK\x03\x04",
    "application/x-zip-compressed": b"PK\x03\x04",
}

#: Audio and video, sniffed to the extent their containers allow. MP3 comes
#: either with an ID3 tag or with a bare frame header, and MP4/MOV/M4A put
#: their `ftyp` box four bytes in — so these are matched at an offset rather
#: than at the start.
_AUDIO_VIDEO_MAGIC: dict[str, tuple[int, tuple[bytes, ...]]] = {
    "audio/mpeg": (0, (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xfa")),
    "audio/ogg": (0, (b"OggS",)),
    "audio/mp4": (4, (b"ftyp",)),
    "video/mp4": (4, (b"ftyp",)),
    "video/quicktime": (4, (b"ftyp", b"moov", b"mdat", b"free", b"wide")),
    "video/webm": (0, (b"\x1a\x45\xdf\xa3",)),
}
_ALLOWED: dict[str, tuple[str, str]] = {
    "image/jpeg": (".jpg", "photo"),
    "image/png": (".png", "photo"),
    "image/gif": (".gif", "photo"),
    "image/webp": (".webp", "photo"),
    "video/mp4": (".mp4", "video"),
    "video/quicktime": (".mov", "video"),
    "video/webm": (".webm", "video"),
    # The delivery block says «файл, ссылка или доступ» and the block editor
    # invites «пришли сюда ссылку или файл» — but a guide is a PDF and a
    # course pack is a ZIP, and neither could be uploaded at all. Every
    # seller of a written product had to host it somewhere else first.
    "application/pdf": (".pdf", "document"),
    "application/zip": (".zip", "document"),
    "application/epub+zip": (".epub", "document"),
    "application/x-zip-compressed": (".zip", "document"),
    "audio/mpeg": (".mp3", "audio"),
    "audio/mp4": (".m4a", "audio"),
    "audio/ogg": (".ogg", "audio"),
}


#: Покупатель видит в чате имя файла из URL — и до этого видел там
#: `3f9c1a…e7.pdf`. Человек платил за гайд, а получал строку из хекса и
#: писал продавцу «это точно тот файл?». Кириллицу в пути пришлось бы
#: процентно кодировать, и до покупателя она доехала бы в том же нечитаемом
#: виде, поэтому русские имена переводятся в латиницу, а не выбрасываются.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "yi", "є": "e", "ґ": "g",
}
_SLUG_MAX = 60


def _slug(original: str | None, ext: str) -> str:
    """`Гайд по продажам.pdf` -> `Gayd-po-prodazham.pdf`.

    Имя приходит от клиента, поэтому от него остаётся только то, что
    заведомо безопасно в пути: латиница, цифры, дефис. Расширение берётся
    наше — то, что мы вывели из Content-Type и уже сверили с магическими
    байтами, а не то, что написано в присланном имени.
    """
    # Обратный слэш заменяется на прямой до разбора: браузеры на Windows
    # присылают полный путь, и `Path` на сервере-линуксе увидел бы в нём
    # одно длинное имя `C-Users-me-otchet`.
    stem = Path((original or "").replace("\\", "/")).name
    if stem.lower().endswith(ext):
        stem = stem[: -len(ext)]
    else:
        stem = stem.rsplit(".", 1)[0] if "." in stem else stem

    out: list[str] = []
    for char in stem:
        lower = char.lower()
        if lower in _TRANSLIT:
            mapped = _TRANSLIT[lower]
            out.append(mapped.capitalize() if char != lower and mapped else mapped)
        elif char.isascii() and char.isalnum():
            out.append(char)
        else:
            out.append("-")

    safe = "".join(out).strip("-")
    while "--" in safe:
        safe = safe.replace("--", "-")
    safe = safe[:_SLUG_MAX].strip("-")
    return f"{safe or 'file'}{ext}"


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile = File(...),
    bot: Bot = Depends(get_owned_bot),
) -> dict:
    content_type = (file.content_type or "").lower()
    match = _ALLOWED.get(content_type)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Неподдерживаемый формат. Можно картинки (JPG, PNG, GIF, WebP), "
                "видео (MP4, MOV, WebM), аудио (MP3, M4A, OGG) и файлы (PDF, ZIP, EPUB)."
            ),
        )
    ext, media_type = match

    settings = get_settings()
    max_bytes = settings.media_max_upload_mb * 1024 * 1024
    # Read one byte past the cap so an oversized upload is caught here,
    # not after buffering the whole thing into memory.
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Файл больше {settings.media_max_upload_mb} МБ — для больших файлов вставь ссылку вместо загрузки",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пустой файл")

    magic = _IMAGE_MAGIC.get(content_type)
    if magic and not data.startswith(magic):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл не похож на заявленный формат")

    riff = _RIFF_MAGIC.get(content_type)
    if riff and not (data.startswith(riff[0]) and data[8:12] == riff[1]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл не похож на заявленный формат")

    doc = _DOC_MAGIC.get(content_type)
    if doc and not data.startswith(doc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл не похож на заявленный формат")

    media_magic = _AUDIO_VIDEO_MAGIC.get(content_type)
    if media_magic:
        offset, signatures = media_magic
        if not any(data[offset:offset + len(sig)] == sig for sig in signatures):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Файл не похож на заявленный формат"
            )

    # A folder per client, which is what makes both the quota below and the
    # sweep in `media_gc` possible at all: with everything in one flat
    # directory there was no way to tell whose bytes were whose. Files
    # uploaded before this stay at the root and keep being served.
    upload_dir = Path(settings.media_upload_dir) / str(bot.client_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    quota = settings.media_quota_mb_per_client * 1024 * 1024
    used = sum(f.stat().st_size for f in upload_dir.glob("*") if f.is_file())
    if used + len(data) > quota:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"Занято {used // 1024 // 1024} МБ из {settings.media_quota_mb_per_client} МБ. "
                f"Удали ненужные файлы из блоков или вставляй ссылки вместо загрузки."
            ),
        )

    # Полный uuid4 (122 бита), не его кусок: файл отдаётся без авторизации, и
    # оплаченный гайд защищён только тем, что адрес нельзя угадать.
    filename = f"{uuid.uuid4().hex}-{_slug(file.filename, ext)}"
    (upload_dir / filename).write_bytes(data)

    url = f"{settings.public_base_url.rstrip('/')}/api/media/{bot.client_id}/{filename}"
    return {"url": url, "media_type": media_type}
