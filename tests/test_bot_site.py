"""Публичная страница продавца: настройки, показ, скрытие, экранирование."""

from __future__ import annotations

from app.models.bot_block import BlockType

FULL = {
    "slug": "my-shop", "title": "Школа <b>йоги</b>", "about": "Онлайн-уроки",
    "seller_name": "ИП Иванов", "seller_id": "БИН 123456789012", "email": "mail@example.com",
}


async def _bot(make_bot, owner, db):
    bot, _ = await make_bot(
        owner,
        [(BlockType.payment, {"title": "Курс «Старт»", "price": "9900", "currency": "KZT", "text": ""})],
    )
    bot.telegram_bot_username = "yoga_test_bot"
    await db.commit()
    return bot


async def test_page_is_hidden_until_enabled_then_shows_products_and_docs(api, auth, owner, make_bot, db):
    bot = await _bot(make_bot, owner, db)
    headers = auth(owner)
    saved = await api.put(f"/api/bots/{bot.id}/site", headers=headers, json=FULL)
    assert saved.status_code == 200 and saved.json()["enabled"] is False
    assert (await api.get("/s/my-shop")).status_code == 404  # ещё не включена

    on = await api.put(f"/api/bots/{bot.id}/site", headers=headers, json={"enabled": True})
    assert on.status_code == 200 and on.json()["url"].endswith("/s/my-shop")

    page = await api.get("/s/my-shop")
    assert page.status_code == 200
    text = page.text
    assert "Курс «Старт»" in text and "9\u202f900 ₸" in text
    assert "https://t.me/yoga_test_bot" in text and "ИП Иванов" in text
    assert "<b>йоги</b>" not in text and "&lt;b&gt;йоги" in text  # чужой текст экранирован

    for doc in ("offer", "refunds", "privacy"):
        res = await api.get(f"/s/my-shop/{doc}")
        assert res.status_code == 200 and "ИП Иванов" in res.text
    assert (await api.get("/s/my-shop/unknown")).status_code == 404


async def test_cannot_enable_without_requisites_or_with_bad_slug(api, auth, owner, make_bot, db):
    bot = await _bot(make_bot, owner, db)
    headers = auth(owner)
    bad = await api.put(f"/api/bots/{bot.id}/site", headers=headers, json={"enabled": True})
    assert bad.status_code == 400 and "название продавца" in bad.json()["detail"]
    assert (await api.put(f"/api/bots/{bot.id}/site", headers=headers, json={"slug": "Ab"})).status_code == 400
    assert (await api.put(f"/api/bots/{bot.id}/site", headers=headers, json={"slug": "api"})).status_code == 400


async def test_slug_is_unique_and_other_owners_cannot_touch_the_page(api, auth, owner, stranger, make_bot, db):
    bot = await _bot(make_bot, owner, db)
    other = await _bot(make_bot, stranger, db)
    assert (await api.put(f"/api/bots/{bot.id}/site", headers=auth(owner), json=FULL)).status_code == 200
    taken = await api.put(f"/api/bots/{other.id}/site", headers=auth(stranger), json={"slug": "my-shop"})
    assert taken.status_code == 409
    assert (await api.get(f"/api/bots/{bot.id}/site", headers=auth(stranger))).status_code == 404


async def test_the_page_disappears_when_its_owner_is_banned_and_payment_text_follows_the_kassa(
    api, auth, owner, make_bot, db
):
    from datetime import datetime, timezone

    bot, _ = await make_bot(
        owner, [(BlockType.payment, {"title": "Гайд", "price": "500", "currency": "XTR"})], provider="stars"
    )
    bot.telegram_bot_username = "stars_shop_bot"
    await db.commit()
    headers = auth(owner)
    await api.put(f"/api/bots/{bot.id}/site", headers=headers, json={**FULL, "slug": "stars-shop", "enabled": True})
    page = (await api.get("/s/stars-shop")).text
    assert "Telegram Stars" in page and "банковской картой" not in page

    owner.banned_at = datetime.now(timezone.utc)
    await db.commit()
    assert (await api.get("/s/stars-shop")).status_code == 404


async def test_a_broken_platform_price_list_is_not_a_free_launch(monkeypatch):
    from app.config import get_settings
    from app.services import payment_service

    settings = get_settings()
    monkeypatch.setattr(settings, "platform_payment_methods", "", raising=False)
    assert payment_service.platform_methods_misconfigured() is False  # пусто: платной публикации нет, так задумано
    monkeypatch.setattr(settings, "platform_payment_methods", "[{oops", raising=False)
    assert payment_service.platform_methods_misconfigured() is True
    monkeypatch.setattr(settings, "platform_payment_methods", '[{"provider":"nope","price_minor":1,"currency":"USD"}]', raising=False)
    assert payment_service.platform_methods_misconfigured() is True
    monkeypatch.setattr(
        settings, "platform_payment_methods", '[{"provider":"stars","price_minor":245000,"currency":"XTR"}]', raising=False
    )
    assert payment_service.platform_methods_misconfigured() is False


async def test_support_chat_is_the_operator_when_no_admins_are_set(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "admin_telegram_ids", "", raising=False)
    monkeypatch.setattr(settings, "support_chat_id", "408204060", raising=False)
    assert settings.admin_ids == {408204060}
    monkeypatch.setattr(settings, "support_chat_id", "-100123", raising=False)  # группа: не оператор
    assert settings.admin_ids == set()
    monkeypatch.setattr(settings, "admin_telegram_ids", "7", raising=False)
    assert settings.admin_ids == {7}


async def test_a_made_up_tax_id_is_refused(api, auth, owner, make_bot, db):
    bot = await _bot(make_bot, owner, db)
    bad = await api.put(f"/api/bots/{bot.id}/site", headers=auth(owner), json={"seller_id": "123"})
    assert bad.status_code == 400 and "10-12 цифр" in bad.json()["detail"]
    ok = await api.put(f"/api/bots/{bot.id}/site", headers=auth(owner), json={"seller_id": "БИН 123456789012"})
    assert ok.status_code == 200
