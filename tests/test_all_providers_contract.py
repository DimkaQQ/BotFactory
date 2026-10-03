"""Общий договор всех касс: ни одна не принимает подделку за оплату.

У каждой кассы свой протокол и свои тесты; здесь проверяется то, что обязано
выполняться у ВСЕХ разом — чтобы новая касса, добавленная без проверки подписи,
не прошла незамеченной.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.models.payment import PaymentStatus
from app.services import payments
from app.services.payments import ProviderError

# `test` подтверждает по открытию ссылки (отключён в бою), `link` — вручную,
# `stars` — апдейтом самого бота: у них нет подписанного уведомления.
NO_SIGNED_CALLBACK = {"test", "link", "stars"}
SIGNED = sorted(set(payments.PROVIDERS) - NO_SIGNED_CALLBACK)


@pytest.mark.parametrize("slug", sorted(payments.PROVIDERS))
def test_every_provider_describes_itself_for_the_settings_form(slug):
    provider = payments.get_provider(slug)
    assert provider.title and provider.currencies and provider.region
    for field in provider.credential_fields:
        assert field.key and field.label


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", SIGNED)
async def test_a_forged_callback_never_marks_a_payment_paid(slug, monkeypatch):
    async def offline(*args, **kwargs):
        raise httpx.ConnectError("нет сети в тесте")

    for name in ("get", "post", "request", "put"):
        monkeypatch.setattr(httpx.AsyncClient, name, offline)

    provider = payments.get_provider(slug)
    credentials = {f.key: "x" for f in provider.credential_fields}
    forged = b'{"status":"paid","type":"checkout.session.completed","data":{"object":{"payment_status":"paid"}}}'
    try:
        result = await provider.verify_webhook(
            headers={"content-type": "application/json"},
            raw_body=forged,
            form={"status": "paid", "OutSum": "990", "InvId": "1", "SignatureValue": "bad"},
            credentials=credentials,
            amount_minor=99000,
            invoice_no=1,
            payment_id=uuid.uuid4(),
            provider_payment_id=None,
            meta={},
            currency=provider.currencies[0],
        )
    except ProviderError:
        return
    except Exception as exc:  # noqa: BLE001 — любой отказ допустим, «оплачено» — нет
        assert not isinstance(exc, AssertionError)
        return
    assert result.status != PaymentStatus.paid, f"{slug} принял подделку за оплату"
