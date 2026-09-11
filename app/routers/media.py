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
_ALLOWED: dict[str, tuple[str, str]] = {
    "image/jpeg": (".jpg", "photo"),
    "image/png": (".png", "photo"),
    "image/gif": (".gif", "photo"),
    "image/webp": (".webp", "photo"),
    "video/mp4": (".mp4", "video"),
    "video/quicktime": (".mov", "video"),
    "video/webm": (".webm", "video"),
}


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
            detail="Неподдерживаемый формат — можно JPG, PNG, GIF, WebP, MP4, MOV или WebM",
        )
    ext, media_type = match

    settings = get_settings()
    max_bytes = settings.media_max_upload_mb * 1024 * 1024
    # Read one byte past the cap so an oversized upload is caught here,
    # not after buffering the whole thing into memory.
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
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

    upload_dir = Path(settings.media_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    (upload_dir / filename).write_bytes(data)

    url = f"{settings.public_base_url.rstrip('/')}/api/media/{filename}"
    return {"url": url, "media_type": media_type}
