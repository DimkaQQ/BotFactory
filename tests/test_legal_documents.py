"""Юридические страницы: все на месте, без реквизитов не публикуются, ссылки сходятся."""

from __future__ import annotations

import re

import pytest

from app.config import get_settings
from app.routers.legal import DOCUMENTS, REVISION

SLUGS = [slug for slug, _title in DOCUMENTS]


@pytest.fixture
def with_requisites(monkeypatch):
    monkeypatch.setenv("LEGAL_NAME", "ИП «Ромашка» & Co")
    monkeypatch.setenv("LEGAL_ID", "ИИН 123456789012")
    monkeypatch.setenv("SUPPORT_TELEGRAM", "bf_support")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", SLUGS)
async def test_every_document_is_published_with_requisites(api, with_requisites, slug):
    response = await api.get(f"/legal/{slug}")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # Реквизиты — на каждой странице, и название не разъезжается в HTML.
    assert "ИП «Ромашка» &amp; Co" in response.text
    assert "«Ромашка» & Co" not in response.text
    assert "ИИН 123456789012" in response.text
    assert f"Редакция от {REVISION}" in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", [*SLUGS, ""])
async def test_nothing_is_published_without_requisites(api, monkeypatch, slug):
    monkeypatch.setenv("LEGAL_NAME", "")
    monkeypatch.setenv("LEGAL_ID", "")
    get_settings.cache_clear()
    try:
        assert (await api.get(f"/legal/{slug}")).status_code == 404
        config = (await api.get("/api/config")).json()
        assert config["legal_docs"] == [] and config["legal_documents"] is False
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_the_config_lists_every_document_for_the_footer(api, with_requisites):
    config = (await api.get("/api/config")).json()
    assert [d["path"] for d in config["legal_docs"]] == [f"/legal/{s}" for s in SLUGS]
    assert all(d["title"] for d in config["legal_docs"])


@pytest.mark.asyncio
async def test_documents_link_to_each_other_and_to_real_pages(api, with_requisites):
    """Ссылка из оферты на несуществующую страницу хуже отсутствия ссылки."""
    index = await api.get("/legal/")
    for slug in SLUGS:
        assert f'href="/legal/{slug}"' in index.text

    for slug in SLUGS:
        body = (await api.get(f"/legal/{slug}")).text
        for target in set(re.findall(r'href="(/legal/[a-z-]*)"', body)):
            assert (await api.get(target)).status_code == 200, f"{slug} ведёт на {target}"


@pytest.mark.asyncio
async def test_the_revision_date_does_not_change_by_itself(api, with_requisites):
    """Документ, датированный «сегодня», получает новую дату каждый день — и
    в споре ни одна редакция не имеет даты."""
    assert re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", REVISION)
    body = (await api.get("/legal/offer")).text
    assert f"Редакция от {REVISION}" in body


@pytest.mark.asyncio
async def test_the_policy_does_not_promise_what_the_service_does_not_do(api, with_requisites):
    """Раньше политика обещала «регулярные резервные копии» всем, хотя они
    настраиваются отдельно. Обещание в юридическом тексте — это обязательство."""
    body = (await api.get("/legal/privacy")).text
    assert "регулярно" not in body
