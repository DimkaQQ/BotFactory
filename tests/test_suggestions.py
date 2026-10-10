"""Идеи владельцев: приём, лимиты, разбор оператором, молчаливый игнор."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.suggestion import Suggestion
from app.services import suggestions


async def test_a_client_can_send_and_see_their_ideas(api, auth, owner, stranger):
    mine, theirs = auth(owner), auth(stranger)
    sent = await api.post("/api/suggestions", headers=mine, json={"text": "Добавьте экспорт клиентов в Excel", "category": "idea"})
    assert sent.status_code == 201 and sent.json()["status"] == "получили, посмотрим"

    listed = (await api.get("/api/suggestions", headers=mine)).json()["suggestions"]
    assert [i["text"] for i in listed] == ["Добавьте экспорт клиентов в Excel"]
    assert (await api.get("/api/suggestions", headers=theirs)).json()["suggestions"] == []  # чужие не видны


async def test_short_long_duplicate_and_too_many_are_refused(api, auth, owner):
    headers = auth(owner)
    assert (await api.post("/api/suggestions", headers=headers, json={"text": "ок"})).status_code == 400
    assert (await api.post("/api/suggestions", headers=headers, json={"text": "x" * 2100})).status_code == 400
    assert (await api.post("/api/suggestions", headers=headers, json={"text": "Сделайте тёмную тему для лендинга"})).status_code == 201
    dup = await api.post("/api/suggestions", headers=headers, json={"text": "  сделайте  тёмную тему для лендинга "})
    assert dup.status_code == 400 and "уже присылали" in dup.json()["detail"]
    for i in range(4):
        assert (await api.post("/api/suggestions", headers=headers, json={"text": f"Идея номер {i} про интерфейс"})).status_code == 201
    over = await api.post("/api/suggestions", headers=headers, json={"text": "Ещё одна совсем другая идея"})
    assert over.status_code == 400 and "завтра" in over.json()["detail"]


async def test_operator_decisions_tell_the_author_only_good_news(db, owner, monkeypatch):
    told = []

    class FakeMeta:
        async def send_message(self, chat_id, text, **_):
            told.append((chat_id, text))

    async def fake_meta():
        return FakeMeta()

    monkeypatch.setattr(suggestions, "_meta", fake_meta)
    owner_tg = owner.telegram_user_id
    item = await suggestions.submit(db, owner, text="Добавьте напоминания клиентам за час")
    item_id = item.id

    await suggestions.set_status(db, item_id, "i")  # плохая идея: молчим
    assert told == []

    await suggestions.set_status(db, item_id, "p")
    assert len(told) == 1 and told[0][0] == owner_tg and "в работу" in told[0][1]
    await suggestions.set_status(db, item_id, "p")  # повторное нажатие автору не пишет
    assert len(told) == 1

    await suggestions.set_status(db, item_id, "d")
    assert len(told) == 2 and "реализована" in told[1][1]
    row = (await db.execute(select(Suggestion).where(Suggestion.id == item_id))).scalar_one()
    assert row.status == "done"
    with pytest.raises(suggestions.SuggestionError):
        await suggestions.set_status(db, item_id, "x")
