"""Раунд ревью 3: сверка сумм без «пустой суммы = ок», чужой счёт в вебхуке lava.top, Payme с не-ASCII."""

from __future__ import annotations

import base64
import json
import uuid

import httpx
import pytest

from app.models.payment import PaymentStatus
from app.services.payments import get_provider
from app.services.payments.base import ProviderError

PAYMENT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
OWN = "c5a0cacc-3453-44b0-9532-aa492f1ba191"
OTHER = "d41db415-ad71-4f2a-8d8c-27eefee91e66"
LAVA = {"api_key": "k", "buyer_email": "shop@example.com"}


async def test_lava_reads_our_own_invoice_not_the_contract_named_in_an_unsigned_body(mock_http):
    """Тело вебхука lava.top не подписано. Чужой оплаченный счёт той же цены не должен
    «оплатить» наш заказ: читаем счёт, id которого сохранён при создании."""
    asked = []

    def handler(req: httpx.Request) -> httpx.Response:
        asked.append(req.url.path.rsplit("/", 1)[-1])
        paid = req.url.path.endswith(OTHER)
        return httpx.Response(
            200, json={"status": "COMPLETED" if paid else "NEW", "receipt": {"amount": 990.0, "currency": "RUB"}}
        )

    forged = json.dumps({"eventType": "payment.success", "contractId": OTHER}).encode()
    with mock_http(handler):
        result = await get_provider("lavatop").verify_webhook(
            headers={}, raw_body=forged, form={}, credentials=LAVA, amount_minor=99000, invoice_no=1,
            payment_id=PAYMENT_ID, provider_payment_id=OWN, currency="RUB",
        )
    assert result.status is PaymentStatus.pending
    assert asked == [OWN]


async def test_lava_refuses_a_contract_id_that_would_leave_the_api_path(mock_http):
    forged = json.dumps({"eventType": "payment.success", "contractId": "../../x"}).encode()
    with pytest.raises(ProviderError):
        await get_provider("lavatop").verify_webhook(
            headers={}, raw_body=forged, form={}, credentials=LAVA, amount_minor=99000, invoice_no=1,
            payment_id=PAYMENT_ID, provider_payment_id=None, currency="RUB",
        )


async def test_yookassa_without_an_amount_is_not_paid(mock_http):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "succeeded", "paid": True, "metadata": {"order_id": str(PAYMENT_ID)}})

    with mock_http(handler), pytest.raises(ProviderError, match="сумма"):
        await get_provider("yookassa").check_status(
            credentials={"shop_id": "1", "secret_key": "k"}, amount_minor=99000, invoice_no=1,
            payment_id=PAYMENT_ID, provider_payment_id="pay-1", meta={}, currency="RUB",
        )


async def test_tbank_without_an_amount_is_not_paid(mock_http):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"Success": True, "ErrorCode": "0", "Status": "CONFIRMED", "OrderId": PAYMENT_ID.hex}
        )

    with mock_http(handler), pytest.raises(ProviderError, match="сумма"):
        await get_provider("tbank").check_status(
            credentials={"terminal_key": "T", "password": "p"}, amount_minor=99000, invoice_no=1,
            payment_id=PAYMENT_ID, provider_payment_id="123", meta={}, currency="RUB",
        )


def test_payme_basic_auth_with_non_ascii_password_is_just_refused():
    from app.services.payments import payme

    header = "Basic " + base64.b64encode("Paycom:ключ".encode()).decode()
    assert payme._authorised({"authorization": header}, "key") is False
    good = "Basic " + base64.b64encode(b"Paycom:key").decode()
    assert payme._authorised({"authorization": good}, "key") is True
