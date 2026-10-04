"""Чеки 54-ФЗ из общей модели, периоды lava.top, регулярные списания LiqPay, сверка Processing.kz."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from decimal import Decimal
from urllib.parse import parse_qs, quote_plus, urlsplit

import pytest

from app.models.payment import PaymentStatus
from app.services.payments import get_provider
from app.services.payments.base import (
    CheckoutRequest,
    PayMethod,
    PayObject,
    ProviderError,
    Receipt,
    ReceiptItem,
    TaxSystem,
    Vat,
    receipt_from_credentials,
)
from app.services.payments.paymaster import receipt_paymaster
from app.services.payments.robokassa import receipt_robokassa
from app.services.payments.tbank import receipt_tbank
from app.services.payments.yookassa import receipt_yookassa

PAYMENT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")


def sample(vat: Vat = Vat.VAT22, price: str = "990.00") -> Receipt:
    return Receipt(
        items=[ReceiptItem(name="Запуск бота", qty=Decimal("1"), price=Decimal(price), vat=vat)],
        tax_system=TaxSystem.USN_INCOME,
        email="shop@example.com",
    )


# ------------------------------------------------------------------ модель


def test_receipt_total_must_equal_the_payment():
    receipt = sample()
    receipt.check(Decimal("990.00"))
    with pytest.raises(ProviderError, match="не совпадает"):
        receipt.check(Decimal("991.00"))


def test_receipt_needs_somewhere_to_send_it():
    bare = Receipt(items=sample().items, tax_system=TaxSystem.OSN)
    with pytest.raises(ProviderError, match="email или телефон"):
        bare.check(Decimal("990.00"))


def test_no_fiscal_email_means_no_receipt_and_a_typo_in_vat_is_loud():
    assert receipt_from_credentials({}, "Гайд", 99000) is None
    with pytest.raises(ProviderError, match="ставка НДС"):
        receipt_from_credentials({"fiscal_email": "a@b.c", "default_vat": "vat20"}, "Гайд", 99000)


def test_receipt_is_built_from_the_shop_settings():
    receipt = receipt_from_credentials(
        {"fiscal_email": "a@b.c", "tax_system": "osn", "default_vat": "vat22"}, "Гайд", 99050
    )
    assert receipt.total() == Decimal("990.50")
    assert receipt.tax_system is TaxSystem.OSN
    assert receipt.items[0].vat is Vat.VAT22
    assert receipt.items[0].method is PayMethod.FULL_PREPAYMENT and receipt.items[0].obj is PayObject.SERVICE


# ------------------------------------------------------------- мапперы касс


def test_yookassa_codes_for_22_percent():
    assert receipt_yookassa(sample(Vat.VAT22))["items"][0]["vat_code"] == 11
    assert receipt_yookassa(sample(Vat.VAT122))["items"][0]["vat_code"] == 12
    item = receipt_yookassa(sample(Vat.NONE))["items"][0]
    assert item["vat_code"] == 1 and item["amount"] == {"value": "990.00", "currency": "RUB"}
    with pytest.raises(ProviderError, match="не сверен"):
        receipt_yookassa(sample(Vat.VAT5))


def test_tbank_receipt_is_in_kopecks_with_new_vat_names():
    out = receipt_tbank(sample(Vat.VAT22, "990.50"))
    item = out["Items"][0]
    assert (item["Price"], item["Amount"], item["Tax"]) == (99050, 99050, "vat22")
    assert out["Taxation"] == "usn_income" and out["Email"] == "shop@example.com"


def test_paymaster_receipt_uses_camel_case_values():
    out = receipt_paymaster(sample(Vat.VAT22))
    assert out["client"] == {"email": "shop@example.com"}
    assert out["items"][0]["vatType"] == "Vat22"
    assert out["items"][0]["paymentMethod"] == "FullPrepayment" and out["items"][0]["paymentSubject"] == "Service"


def test_robokassa_receipt_shape():
    out = receipt_robokassa(sample())
    assert out["sno"] == "usn_income"
    assert out["items"][0]["sum"] == 990.0 and out["items"][0]["tax"] == "vat22"


async def test_robokassa_signs_the_once_encoded_receipt_and_the_link_encodes_it_twice():
    creds = {
        "merchant_login": "shop", "password1": "pass1", "password2": "pass2",
        "test_password1": "tp1", "test_password2": "tp2",
        "fiscal_email": "shop@example.com", "tax_system": "usn_income", "default_vat": "vat22",
    }
    request = CheckoutRequest(
        payment_id=PAYMENT_ID, invoice_no=77, amount_minor=99000, currency="RUB", description="Запуск бота",
        return_url="https://t.me/x", is_test=False, credentials=creds,
    )
    checkout = await get_provider("robokassa").create_checkout(request)

    query = urlsplit(checkout.url).query
    # Значение в ссылке закодировано дважды: после разбора ссылки остаётся одно кодирование.
    receipt_once = parse_qs(query)["Receipt"][0]
    raw = json.dumps(receipt_robokassa(sample()), ensure_ascii=False, separators=(",", ":"))
    assert receipt_once == quote_plus(raw)
    assert quote_plus(receipt_once) in query

    expected = hashlib.md5(f"shop:990.00:77:{receipt_once}:pass1".encode()).hexdigest()
    assert parse_qs(query)["SignatureValue"][0] == expected


async def test_robokassa_without_fiscal_email_signs_the_old_way():
    creds = {"merchant_login": "shop", "password1": "pass1", "password2": "pass2"}
    request = CheckoutRequest(
        payment_id=PAYMENT_ID, invoice_no=77, amount_minor=99000, currency="RUB", description="x",
        return_url="https://t.me/x", is_test=False, credentials=creds,
    )
    checkout = await get_provider("robokassa").create_checkout(request)
    query = parse_qs(urlsplit(checkout.url).query)
    assert "Receipt" not in query
    assert query["SignatureValue"][0] == hashlib.md5(b"shop:990.00:77:pass1").hexdigest()


# --------------------------------------------------------------- lava.top


def test_lava_prefers_the_period_chosen_from_the_offer():
    from app.services.payments.lavatop import _periodicity

    assert _periodicity({"subscription": True, "period_days": 30, "periodicity": "PERIOD_90_DAYS"}) == "PERIOD_90_DAYS"
    assert _periodicity({"subscription": True, "period_days": 30}) == "MONTHLY"
    assert _periodicity({"subscription": False, "periodicity": "MONTHLY"}) == "ONE_TIME"


async def test_lava_refuses_an_offer_without_that_price(monkeypatch):
    from app.services.payments import lavatop

    async def prices(api_key):
        return [{"offer_id": "o1", "product": "P", "currency": "RUB", "amount": 990, "periodicity": "MONTHLY"}]

    monkeypatch.setattr(lavatop, "offer_prices", prices)
    provider = get_provider("lavatop")
    await provider._check_offer_price({"api_key": "k"}, "o1", "RUB", "MONTHLY")
    with pytest.raises(ProviderError, match="нет цены RUB/PERIOD_YEAR"):
        await provider._check_offer_price({"api_key": "k"}, "o1", "RUB", "PERIOD_YEAR")


# ----------------------------------------------------------------- LiqPay

LIQ_CREDS = {"public_key": "i123", "private_key": "priv"}


def liq_data(**fields) -> dict:
    payload = {"order_id": str(PAYMENT_ID), "amount": 990.0, "currency": "UAH", **fields}
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    sig = base64.b64encode(hashlib.sha1(f"priv{data}priv".encode()).digest()).decode()
    return {"data": data, "signature": sig}


async def liq(form, meta=None):
    return await get_provider("liqpay").verify_webhook(
        headers={}, raw_body=b"", form=form, credentials=LIQ_CREDS, amount_minor=99000, invoice_no=1,
        payment_id=PAYMENT_ID, provider_payment_id=None, meta=meta or {"liqpay_test": False}, currency="UAH",
    )


async def test_liqpay_regular_charge_is_a_renewal_keyed_by_the_gateway_payment_id():
    result = await liq(liq_data(status="success", action="regular", payment_id=555))
    assert result.status is PaymentStatus.paid
    assert result.meta == {"gateway_renewal": "555"}

    first = await liq(liq_data(status="success", action="pay", payment_id=556))
    assert first.status is PaymentStatus.paid and first.meta == {}


async def test_liqpay_subscription_events():
    assert (await liq(liq_data(status="subscribed", action="subscribe"))).status is PaymentStatus.pending
    gone = await liq(liq_data(status="unsubscribed"))
    assert gone.status is PaymentStatus.pending and gone.meta == {"gateway_unsubscribed": True}
    failed = await liq(liq_data(status="failure", action="regular", err_description="no money"))
    assert failed.status is PaymentStatus.pending and not failed.meta


# ----------------------------------------------------------- Processing.kz


async def test_processingkz_rejects_a_wrong_amount_before_capturing(monkeypatch):
    from app.services.payments import processingkz

    provider = processingkz.ProcessingKzProvider()
    calls = []

    async def read(self, endpoint, merchant, reference):
        return "AUTHORISED", 5000, "398"

    async def complete(self, endpoint, merchant, reference, *, success=True):
        calls.append(success)

    monkeypatch.setattr(processingkz.ProcessingKzProvider, "_read", read)
    monkeypatch.setattr(processingkz.ProcessingKzProvider, "_complete", complete)
    result = await provider.check_status(
        credentials={"merchant_id": "m"}, amount_minor=99000, invoice_no=1, payment_id=PAYMENT_ID,
        provider_payment_id="ref", meta={"is_test": True}, currency="KZT",
    )
    assert calls == [False], "холд надо снять, а не списать"
    assert result.status is PaymentStatus.failed


# ------------------------------------------------- переключатель «передавать чек»


def test_receipt_goes_out_only_when_the_seller_switched_it_on():
    from app.services.payments.base import fiscalization_enabled

    # Почта заполнена, но переключатель выключен явно — чека нет (касса без онлайн-кассы).
    assert receipt_from_credentials({"fiscal_email": "a@b.c", "fiscalization_enabled": "0"}, "Гайд", 99000) is None
    # Пусто и почты нет — тоже нет.
    assert receipt_from_credentials({}, "Гайд", 99000) is None
    # Включено — чек есть.
    on = receipt_from_credentials({"fiscal_email": "a@b.c", "fiscalization_enabled": "1"}, "Гайд", 99000)
    assert on is not None and on.email == "a@b.c"
    # Включено без почты — внятная ошибка, а не платёж, который касса отклонит.
    with pytest.raises(ProviderError, match="не указана почта"):
        receipt_from_credentials({"fiscalization_enabled": "1"}, "Гайд", 99000)
    # Настройки, сохранённые до появления переключателя (поля нет, почта есть), работают как работали.
    assert fiscalization_enabled({"fiscal_email": "a@b.c"}) is True
    assert fiscalization_enabled({"fiscal_email": "a@b.c", "fiscalization_enabled": "нет"}) is False


async def test_a_seller_with_a_fiscal_kassa_and_no_email_is_told_what_is_missing(api, auth, owner, make_bot, db):

    bot, _ = await make_bot(
        owner, [], provider="yookassa", is_test=False,
        credentials={"shop_id": "1", "secret_key": "live_x", "fiscalization_enabled": "1"},
    )
    response = await api.get(f"/api/bots/{bot.id}/payment-settings", headers=auth(owner))
    body = response.json()
    assert body["ready"] is False
    assert any("Почта для чеков" in label for label in body["missing_fields"])
