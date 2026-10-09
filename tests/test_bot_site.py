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
    assert "Курс «Старт»" in text and "9900 ₸" in text
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
