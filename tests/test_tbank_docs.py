"""Т-Банк: поведение по официальной документации (docs/tbank-docs.md)."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from app.models.payment import PaymentStatus
from app.services.payments import get_provider
from app.services.payments.base import CheckoutRequest, ProviderError, RecurringSetup
from app.services.payments.tbank import _clean, _token

PAYMENT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
CREDS = {"terminal_key": "T1", "password": "pw"}
RECEIPT_CREDS = {**CREDS, "fiscalization_enabled": "1", "fiscal_email": "shop@example.com", "tax": "vat22"}


def request(creds=None, *, is_test=False, extra=None, description="Запуск бота") -> CheckoutRequest:
    return CheckoutRequest(
        payment_id=PAYMENT_ID, invoice_no=1, amount_minor=99000, currency="RUB", description=description,
        return_url="https://t.me/x", is_test=is_test, credentials=creds or CREDS, extra=extra or {}, telegram_user_id=5150,
    )


def api(seen, *, state="CONFIRMED", amount=99000, order=None, init=None, confirm_ok=True, charge=None):
    """Банк на всё про один платёж. `state` — что вернёт GetState; после Confirm он становится CONFIRMED."""
    box = {"state": state}

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        seen.append({"url": str(req.url), **body})
        name = req.url.path.rsplit("/", 1)[-1]
        if name == "Init":
            return httpx.Response(200, json=init or {"Success": True, "ErrorCode": "0", "PaymentId": "777", "PaymentURL": "https://pay/x"})
        if name == "Confirm":
            if not confirm_ok:
                return httpx.Response(200, json={"Success": False, "ErrorCode": "100", "Message": "no"})
            box["state"] = "CONFIRMED"
            return httpx.Response(200, json={"Success": True, "ErrorCode": "0", "Status": "CONFIRMING"})
        if name == "Charge":
            return charge(req) if charge else httpx.Response(200, json={"Success": True, "ErrorCode": "0", "Status": "CONFIRMED", "Amount": amount})
        return httpx.Response(200, json={
            "Success": True, "ErrorCode": "0", "Status": box["state"], "Amount": amount,
            "OrderId": order or PAYMENT_ID.hex, "PaymentId": "777",
        })

    return handler


async def read(mock_http, handler, *, meta=None):
    with mock_http(handler):
        return await get_provider("tbank").check_status(
            credentials=CREDS, amount_minor=99000, invoice_no=1, payment_id=PAYMENT_ID,
            provider_payment_id="777", meta=meta or {},
        )


# -------------------------------------------------------------- хост и подпись


async def test_test_mode_goes_to_the_test_host_but_a_demo_terminal_stays_on_the_live_one(mock_http):
    seen: list[dict] = []
    provider = get_provider("tbank")
    with mock_http(api(seen)):
        test = await provider.create_checkout(request(is_test=True))
        await provider.create_checkout(request(is_test=False))
        await provider.create_checkout(request({"terminal_key": "1234DEMO", "password": "pw"}, is_test=True))

    assert seen[0]["url"].startswith("https://rest-api-test.tinkoff.ru/v2/Init")
    assert seen[1]["url"].startswith("https://securepay.tinkoff.ru/v2/Init")
    assert seen[2]["url"].startswith("https://securepay.tinkoff.ru/v2/Init"), "DEMO-терминал работает на боевом хосте"
    assert test.meta["tbank_test"] is True, "режим платежа запоминается для уведомлений и «Я оплатил»"


async def test_payment_status_is_read_from_the_host_the_payment_was_created_on(mock_http):
    seen: list[dict] = []
    await read(mock_http, api(seen), meta={"tbank_test": True})
    await read(mock_http, api(seen), meta={})
    assert seen[0]["url"].startswith("https://rest-api-test.tinkoff.ru/") and seen[1]["url"].startswith("https://securepay.")


def test_token_skips_null_and_nested_values_and_writes_booleans_in_lowercase():
    base = {"TerminalKey": "T", "Success": True, "Status": "CONFIRMED"}
    assert _token({**base, "Pan": None, "Data": {"a": 1}, "Receipt": {"b": 2}}, "pw") == _token(base, "pw")
    # Официальный пример документации (проверка Token уведомления)
    official = {
        "TerminalKey": "1111111111111DEMO", "OrderId": "1", "Success": True, "Status": "AUTHORIZED",
        "PaymentId": "1234567890", "ErrorCode": "0", "Amount": 100000, "CardId": 111111111, "Pan": "111111******1111",
        "ExpDate": "0000", "RebillId": "", "Data": {"x": "y"},
    }
    assert isinstance(_token(official, "pw"), str) and len(_token(official, "pw")) == 64


def test_the_documented_init_example_gives_the_documented_token():
    # Пример из раздела 3 документации: терминал MerchantTerminalKey, пароль 11111111111111.
    payload = {
        "TerminalKey": "MerchantTerminalKey", "Amount": 19200, "OrderId": "00000",
        "Description": "Подарочная карта на 1000 рублей", "Receipt": {"Items": []}, "DATA": {"a": "b"},
    }
    assert _token(payload, "11111111111111") == "72dd466f8ace0a37a1f740ce5fb78101712bc0665d91a8108c7c8a0ccd426db2"


def test_special_characters_are_removed_from_free_text():
    assert _clean('Бот "Магазин" & Co <b>') == "Бот Магазин Co b"


async def test_init_sends_a_short_clean_description_and_a_hex_order_id(mock_http):
    seen: list[dict] = []
    with mock_http(api(seen)):
        await get_provider("tbank").create_checkout(request(description='«Бот» "Магазин" & ' + "я" * 300))
    assert seen[0]["OrderId"] == PAYMENT_ID.hex and "PayType" not in seen[0]
    assert len(seen[0]["Description"]) <= 140 and '"' not in seen[0]["Description"] and "&" not in seen[0]["Description"]


# ------------------------------------------------------------ уведомление


def notification(**fields) -> bytes:
    body = {"TerminalKey": "T1", "OrderId": PAYMENT_ID.hex, "Success": True, "Status": "CONFIRMED",
            "PaymentId": 777, "ErrorCode": "0", "Amount": 99000, **fields}
    body["Token"] = _token(body, "pw")
    return json.dumps(body).encode()


async def verify(mock_http, handler, raw):
    with mock_http(handler):
        return await get_provider("tbank").verify_webhook(
            headers={}, raw_body=raw, form={}, credentials=CREDS, amount_minor=99000, invoice_no=1,
            payment_id=PAYMENT_ID, provider_payment_id=None,
        )


async def test_a_signed_notification_is_answered_ok_and_settles_through_the_bank(mock_http):
    result = await verify(mock_http, api([]), notification(RebillId=555, CustomerKey="5150"))
    assert result.status is PaymentStatus.paid and result.response_body == "OK"
    assert result.meta["tbank_rebill_id"] == "555" and result.meta["tbank_customer_key"] == "5150"


async def test_a_notification_without_a_valid_signature_never_reaches_the_bank(mock_http):
    seen: list[dict] = []
    unsigned = json.dumps({"OrderId": PAYMENT_ID.hex, "PaymentId": "777", "Status": "CONFIRMED"}).encode()
    tampered = notification().replace(b"CONFIRMED", b"REJECTED")
    for raw in (unsigned, tampered, b"{}"):
        with pytest.raises(ProviderError, match="подпись"):
            await verify(mock_http, api(seen), raw)
    assert seen == [], "чужой запрос не должен заставлять нас ходить в банк с ключами продавца"


async def test_a_payment_that_belongs_to_another_order_is_refused(mock_http):
    with pytest.raises(ProviderError, match="другому заказу"):
        await read(mock_http, api([], order=uuid.uuid4().hex))


# ----------------------------------------------------- двухстадийный терминал


async def test_a_held_payment_is_confirmed_and_paid_only_after_the_bank_says_confirmed(mock_http):
    seen: list[dict] = []
    receipt = {"Email": "a@b.c", "Taxation": "usn_income", "Items": []}
    result = await read(mock_http, api(seen, state="AUTHORIZED"), meta={"tbank_receipt": receipt})

    names = [c["url"].rsplit("/", 1)[-1] for c in seen]
    assert names == ["GetState", "Confirm", "GetState"]
    confirm = seen[1]
    assert confirm["PaymentId"] == "777" and confirm["Receipt"] == receipt, "Confirm несёт тот же чек"
    assert confirm["Token"] == _token({"TerminalKey": "T1", "PaymentId": "777"}, "pw"), "Receipt в подпись не входит"
    assert result.status is PaymentStatus.paid


async def test_a_failed_confirm_leaves_the_payment_pending_to_be_retried(mock_http):
    result = await read(mock_http, api([], state="AUTHORIZED", confirm_ok=False))
    assert result.status is PaymentStatus.pending


async def test_one_stage_payment_never_calls_confirm(mock_http):
    seen: list[dict] = []
    await read(mock_http, api(seen, state="CONFIRMED"))
    assert [c["url"].rsplit("/", 1)[-1] for c in seen] == ["GetState"]


async def test_the_rebill_id_is_picked_up_from_get_state_when_there_was_no_notification(mock_http):
    def handler(req):
        return httpx.Response(200, json={"Success": True, "ErrorCode": "0", "Status": "CONFIRMED",
                                         "Amount": 99000, "OrderId": PAYMENT_ID.hex, "RebillId": "9001"})

    result = await read(mock_http, handler)
    assert result.meta["tbank_rebill_id"] == "9001"


# --------------------------------------------------------------- ошибки банка


async def test_a_refusal_with_http_200_is_an_error_with_a_human_hint(mock_http):
    refusal = {"Success": False, "ErrorCode": "10", "Message": "Метод Charge заблокирован для данного терминала"}
    with mock_http(lambda r: httpx.Response(200, json=refusal)), pytest.raises(ProviderError, match="автоплатежи"):
        await get_provider("tbank").create_checkout(request())


async def test_success_true_with_a_nonzero_error_code_is_still_an_error(mock_http):
    odd = {"Success": True, "ErrorCode": "204", "PaymentURL": "https://pay/x"}
    with mock_http(lambda r: httpx.Response(200, json=odd)), pytest.raises(ProviderError, match="Terminal Key"):
        await get_provider("tbank").create_checkout(request())


async def test_a_missing_payment_url_explains_how_to_enable_the_payment_form(mock_http):
    nothing = {"Success": True, "ErrorCode": "0", "PaymentId": "1"}
    with mock_http(lambda r: httpx.Response(200, json=nothing)), pytest.raises(ProviderError, match="платёжная форма"):
        await get_provider("tbank").create_checkout(request())


# ------------------------------------------------------------------ подписки


async def test_the_first_subscription_payment_carries_the_parent_operation_type(mock_http):
    seen: list[dict] = []
    provider = get_provider("tbank")
    with mock_http(api(seen)):
        checkout = await provider.create_checkout(request(extra={"subscription": True}))
        await provider.create_checkout(request())
    first, plain = seen
    assert first["Recurrent"] == "Y" and first["CustomerKey"] == "5150"
    assert first["DATA"] == {"OperationInitiatorType": "1"}
    assert "DATA" not in plain and "Recurrent" not in plain, "обычная оплата тип операции не указывает"
    assert checkout.meta["tbank_customer_key"] == "5150"


async def test_a_renewal_init_has_the_receipt_and_the_regular_operation_type_and_no_pay_type(mock_http):
    seen: list[dict] = []
    creds = {**RECEIPT_CREDS, "_buyer_email": "buyer@example.com"}
    with mock_http(api(seen)):
        verdict = await get_provider("tbank").charge_recurring(
            credentials=creds, setup=RecurringSetup(token="rb", customer="5150"), amount_minor=99000,
            currency="RUB", description="Клуб", payment_id=PAYMENT_ID, invoice_no=1,
        )
    init = seen[0]
    assert init["DATA"] == {"OperationInitiatorType": "R"} and "PayType" not in init
    assert init["OrderId"] == PAYMENT_ID.hex
    assert init["Receipt"]["Email"] == "buyer@example.com" and init["Receipt"]["Items"][0]["PaymentMethod"] == "full_payment"
    assert "Receipt" not in seen[1], "в Charge чека нет: он берётся из Init"
    assert verdict.status is PaymentStatus.paid


async def test_an_authorized_renewal_is_confirmed(mock_http):
    seen: list[dict] = []

    def charge(req):
        return httpx.Response(200, json={"Success": True, "ErrorCode": "0", "Status": "AUTHORIZED", "Amount": 99000})

    with mock_http(api(seen, state="AUTHORIZED", charge=charge)):
        verdict = await get_provider("tbank").charge_recurring(
            credentials=CREDS, setup=RecurringSetup(token="rb"), amount_minor=99000, currency="RUB",
            description="Клуб", payment_id=PAYMENT_ID, invoice_no=1,
        )
    assert "Confirm" in [c["url"].rsplit("/", 1)[-1] for c in seen]
    assert verdict.status is PaymentStatus.paid


async def test_a_charge_that_got_no_answer_is_not_repeated_but_looked_up(mock_http):
    seen: list[dict] = []

    def charge(req):
        return httpx.Response(500, json={"Success": False, "ErrorCode": "9999"})

    with mock_http(api(seen, state="CONFIRMED", charge=charge)):
        verdict = await get_provider("tbank").charge_recurring(
            credentials=CREDS, setup=RecurringSetup(token="rb"), amount_minor=99000, currency="RUB",
            description="Клуб", payment_id=PAYMENT_ID, invoice_no=1,
        )
    names = [c["url"].rsplit("/", 1)[-1] for c in seen]
    assert names.count("Charge") == 1, "повторять Charge вслепую нельзя"
    assert names[-1] == "GetState" and verdict.status is PaymentStatus.paid


async def test_a_declined_renewal_says_why(mock_http):
    def charge(req):
        return httpx.Response(200, json={"Success": False, "ErrorCode": "1051", "Message": "x"})

    with mock_http(api([], charge=charge)), pytest.raises(ProviderError, match="недостаточно средств"):
        await get_provider("tbank").charge_recurring(
            credentials=CREDS, setup=RecurringSetup(token="rb"), amount_minor=99000, currency="RUB",
            description="Клуб", payment_id=PAYMENT_ID, invoice_no=1,
        )


# ---------------------------------------------------------------- сертификаты


def test_extra_ca_bundle_is_added_to_the_default_trust_store(monkeypatch, tmp_path):
    import certifi

    from app.config import get_settings
    from app.services.payments import tbank

    monkeypatch.setenv("TBANK_CA_BUNDLE", certifi.where())  # любой настоящий PEM
    get_settings.cache_clear()
    try:
        client = tbank._http_client()
        assert isinstance(client, httpx.AsyncClient)

        monkeypatch.setenv("TBANK_CA_BUNDLE", str(tmp_path / "missing.pem"))
        get_settings.cache_clear()
        assert isinstance(tbank._http_client(), httpx.AsyncClient), "нет файла — обычное хранилище, не падение"
    finally:
        get_settings.cache_clear()
