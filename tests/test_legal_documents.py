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


@pytest.fixture
def with_agent(monkeypatch, with_requisites):
    monkeypatch.setenv("AGENT_NAME", "MoraAgency OÜ")
    monkeypatch.setenv("AGENT_ID", "Registry code 17094028")
    monkeypatch.setenv("AGENT_ADDRESS", "Kuldnoka 5, Tallinn")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_documents_stay_silent_about_an_agent_that_does_not_exist(api, with_requisites):
    for slug in SLUGS:
        assert "платёжный агент" not in (await api.get(f"/legal/{slug}")).text.lower(), slug
    assert (await api.get("/api/config")).json()["payment_agent"] == ""


@pytest.mark.asyncio
async def test_the_agent_is_named_and_is_not_a_party_to_the_contract(api, with_agent):
    offer = (await api.get("/legal/offer")).text
    assert "MoraAgency OÜ" in offer and "17094028" in offer
    assert "от имени и по поручению Исполнителя" in offer
    assert "не является стороной договора" in offer
    # Исполнитель по-прежнему тот, кто в LEGAL_NAME.
    assert "ИП «Ромашка» &amp; Co" in offer

    for slug in ("refunds", "privacy", "data-processing"):
        assert "MoraAgency OÜ" in (await api.get(f"/legal/{slug}")).text, slug

    config = (await api.get("/api/config")).json()
    assert config["payment_agent"] == "MoraAgency OÜ"


@pytest.mark.asyncio
async def test_an_agent_without_a_registration_number_is_ignored(api, with_requisites, monkeypatch):
    """Агент без номера — это не агент, а строка без реквизитов: хуже отсутствия."""
    monkeypatch.setenv("AGENT_NAME", "MoraAgency OÜ")
    monkeypatch.setenv("AGENT_ID", "")
    get_settings.cache_clear()
    try:
        assert "MoraAgency" not in (await api.get("/legal/offer")).text
    finally:
        get_settings.cache_clear()


# ------------------------------------------------------------- English


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", SLUGS)
async def test_every_document_has_an_english_version(api, with_requisites, slug):
    response = await api.get(f"/legal/{slug}?lang=en")
    assert response.status_code == 200
    body = response.text
    assert '<html lang="en">' in body
    assert "ИП «Ромашка» &amp; Co" in body, "реквизиты пропали из английской версии"
    # Английская версия не должна случайно остаться русской.
    assert len(re.findall(r"[А-Яа-я]{4,}", re.sub(r"ИП «Ромашка» &amp; Co|ИИН \d+|Русский", "", body))) == 0, slug
    assert f"Revision of {REVISION}" in body


@pytest.mark.asyncio
async def test_english_documents_link_to_english_pages_and_back(api, with_requisites):
    index = await api.get("/legal/?lang=en")
    assert index.status_code == 200 and 'href="/legal/offer?lang=en"' in index.text
    for slug in SLUGS:
        body = (await api.get(f"/legal/{slug}?lang=en")).text
        assert f'href="/legal/{slug}"' in body, "нет ссылки на русскую версию"
        for target in set(re.findall(r'href="(/legal/[a-z-]*)\?lang=en"', body)):
            assert (await api.get(f"{target}?lang=en")).status_code == 200, f"{slug} ведёт на {target}"


@pytest.mark.asyncio
async def test_russian_pages_offer_the_switch_to_english(api, with_requisites):
    assert 'href="/legal/offer?lang=en"' in (await api.get("/legal/offer")).text


@pytest.mark.asyncio
async def test_an_unknown_language_falls_back_to_russian(api, with_requisites):
    assert '<html lang="ru">' in (await api.get("/legal/offer?lang=fr")).text


@pytest.mark.asyncio
async def test_english_pages_are_not_published_without_requisites(api, monkeypatch):
    monkeypatch.setenv("LEGAL_NAME", "")
    monkeypatch.setenv("LEGAL_ID", "")
    get_settings.cache_clear()
    try:
        for slug in SLUGS:
            assert (await api.get(f"/legal/{slug}?lang=en")).status_code == 404
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_the_english_offer_names_the_agent_and_prices(api, with_agent):
    body = (await api.get("/legal/offer?lang=en")).text
    assert "MoraAgency OÜ" in body and "on behalf of and on the instructions of the Provider" in body
    assert "not a party to the contract" in body


# ------------------------------------------------- GDPR, VAT, server location


@pytest.mark.asyncio
async def test_the_privacy_policy_carries_the_gdpr_rights(api, with_requisites):
    ru = (await api.get("/legal/privacy")).text
    en = (await api.get("/legal/privacy?lang=en")).text
    assert "Andmekaitse Inspektsioon" in ru and "Andmekaitse Inspektsioon" in en
    assert "6(1)(b)" in ru and "6(1)(b)" in en
    assert "Ваши права" in ru and "Your rights" in en


@pytest.mark.asyncio
async def test_server_location_is_named_only_when_it_is_configured(api, with_requisites, monkeypatch):
    assert "Серверы сервиса расположены" not in (await api.get("/legal/privacy")).text
    monkeypatch.setenv("DATA_LOCATION", "Нидерланды")
    get_settings.cache_clear()
    try:
        assert "расположены в: Нидерланды" in (await api.get("/legal/privacy")).text
        monkeypatch.setenv("DATA_LOCATION", "Netherlands")
        get_settings.cache_clear()
        assert "located in: Netherlands" in (await api.get("/legal/privacy?lang=en")).text
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_the_vat_number_appears_only_when_set(api, with_requisites, monkeypatch):
    assert "VAT" not in (await api.get("/legal/offer")).text
    monkeypatch.setenv("LEGAL_VAT", "EE123456789")
    get_settings.cache_clear()
    try:
        assert "НДС (VAT): EE123456789" in (await api.get("/legal/offer")).text
        assert "VAT: EE123456789" in (await api.get("/legal/offer?lang=en")).text
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_governing_law_appears_only_when_the_country_is_set(api, with_requisites, monkeypatch):
    ru = (await api.get("/legal/offer")).text
    assert "Применимое право" not in ru

    monkeypatch.setenv("LEGAL_COUNTRY", "Эстония")
    get_settings.cache_clear()
    ru = (await api.get("/legal/offer")).text
    en = (await api.get("/legal/offer?lang=en")).text
    assert "Применимое право и споры" in ru and "Эстония" in ru
    assert "Governing law and disputes" in en and "Estonia" in en
    assert "Автоматических списаний нет" in ru and "no automatic charges" in en
