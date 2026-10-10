"""Защиты, добавленные по итогам аудита."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.models.client import Client
from app.services.payments import ProviderError

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.asyncio
async def test_api_docs_are_closed_by_default(api):
    for path in ("/docs", "/redoc", "/openapi.json"):
        response = await api.get(path)
        assert response.status_code == 404, f"{path} раскрывает API всем подряд"


@pytest.mark.asyncio
async def test_uploaded_file_name_cannot_be_guessed(api, auth, owner: Client, make_bot):
    bot, _ = await make_bot(owner, [])
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    response = await api.post(
        f"/api/bots/{bot.id}/media/upload",
        headers=auth(owner),
        files={"file": ("guide.png", png, "image/png")},
    )
    assert response.status_code == 201
    name = response.json()["url"].rsplit("/", 1)[-1]
    assert re.match(r"^[0-9a-f]{32}-guide\.png$", name), name


def test_signatures_are_compared_in_constant_time():
    """Три адаптера сравнивали подпись через `!=` — по времени ответа её можно
    подобрать побайтно. Проверяем сам исходник: наивного сравнения быть не
    должно, и это дешевле, чем мерить наносекунды."""
    for slug in ("robokassa", "click", "freedompay"):
        source = (ROOT / "app" / "services" / "payments" / f"{slug}.py").read_text()
        assert "hmac.compare_digest(received" in source, slug
        assert not re.search(r"received\s*!=", source), slug


def test_xml_from_a_provider_cannot_expand_entities():
    """Ответ провайдера разбирается defusedxml: «бомба» из сущностей и внешние
    сущности отвергаются, а не раскрываются."""
    from defusedxml.common import DefusedXmlException

    from app.services.payments import freedompay, processingkz

    bomb = (
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        "<response>&b;</response>"
    )
    for parse in (freedompay._parse_xml, processingkz.ET.fromstring):
        with pytest.raises((DefusedXmlException, ProviderError)):
            parse(bomb)



def test_background_tasks_can_be_moved_out_of_the_api(monkeypatch):
    """api без фоновых задач (RUN_BACKGROUND=false) — основа плавного обновления: фоновую
    работу ведёт отдельный worker, а api можно запускать в нескольких экземплярах."""
    import asyncio

    from fastapi import FastAPI

    from app import main
    from app.config import get_settings

    started = []
    monkeypatch.setattr(main, "start_background_tasks", lambda: started.append(1))

    async def run(flag: str) -> None:
        monkeypatch.setenv("RUN_BACKGROUND", flag)
        get_settings.cache_clear()
        try:
            async with main.lifespan(FastAPI()):
                pass
        finally:
            get_settings.cache_clear()

    asyncio.run(run("false"))
    assert started == []
    asyncio.run(run("true"))
    assert started == [1]
