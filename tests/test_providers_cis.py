"""The gateways a seller in the CIS actually has: RF, KZ, UZ, KG, UA.

Same two families as the older providers, and the same discipline: every
signature is recomputed here from the published scheme rather than by
calling the adapter's own helper, so a change to the adapter that quietly
breaks the scheme fails a test instead of a real payment.

The two protocols that are conversations rather than notifications — Click's
Prepare/Complete and Payme's JSON-RPC — get their own sections, because
what has to be right there is the *sequence*, not one message.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid

import httpx
import pytest

from app.services.payments import get_provider
from app.services.payments.base import CheckoutRequest, ProviderError

PAYMENT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def checkout_request(credentials: dict, *, amount_minor: int = 99000, currency: str = "RUB", **extra):
    return CheckoutRequest(
        payment_id=PAYMENT_ID,
        invoice_no=4242,
        amount_minor=amount_minor,
        currency=currency,
        description="Гайд по кофейне",
        return_url="https://t.me/some_bot",
        is_test=True,
        credentials=credentials,
        **extra,
    )


# -------------------------------------------------------------------- LiqPay

LIQPAY_CREDS = {"public_key": "i123456789", "private_key": "priv_key_value"}


def liqpay_sign(data: str, private_key: str = "priv_key_value") -> str:
    """The scheme as the official SDK states it, recomputed here."""
    joined = f"{private_key}{data}{private_key}".encode()
    return base64.b64encode(hashlib.sha1(joined).digest()).decode()


def liqpay_callback(status: str = "success", amount: float = 990.0) -> dict:
    payload = {
        "order_id": str(PAYMENT_ID),
        "status": status,
        "amount": amount,
        "currency": "UAH",
        "payment_id": 55667788,
    }
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    return {"data": data, "signature": liqpay_sign(data)}


async def test_liqpay_hands_out_a_link_to_a_form_it_cannot_get():
    """LiqPay's checkout is a POST. A bot button can only carry a link, so
    the link has to point at a page of ours that posts the form."""
    checkout = await get_provider("liqpay").create_checkout(
        checkout_request(LIQPAY_CREDS, currency="UAH")
    )

    assert f"/api/pay/redirect/{PAYMENT_ID}" in checkout.url
    assert checkout.meta["form_action"] == "https://www.liqpay.ua/api/3/checkout/"

    fields = checkout.meta["form_fields"]
    assert fields["signature"] == liqpay_sign(fields["data"])
    params = json.loads(base64.b64decode(fields["data"]))
    assert params["order_id"] == str(PAYMENT_ID)
    assert params["amount"] == "990.00"
    assert params["sandbox"] == 1


async def test_liqpay_accepts_its_own_signed_callback():
    result = await get_provider("liqpay").verify_webhook(
        headers={}, raw_body=b"", form=liqpay_callback(),
        credentials=LIQPAY_CREDS, amount_minor=99000, invoice_no=4242,
        payment_id=PAYMENT_ID, provider_payment_id=None,
    )

    assert result.status.value == "paid"
    assert result.provider_payment_id == "55667788"


async def test_liqpay_refuses_a_callback_signed_with_someone_elses_key():
    form = liqpay_callback()
    form["signature"] = liqpay_sign(form["data"], private_key="other_shops_key")

    with pytest.raises(ProviderError, match="подпись"):
        await get_provider("liqpay").verify_webhook(
            headers={}, raw_body=b"", form=form,
            credentials=LIQPAY_CREDS, amount_minor=99000, invoice_no=4242,
            payment_id=PAYMENT_ID, provider_payment_id=None,
        )


async def test_liqpay_refuses_a_correctly_signed_callback_for_less_money():
    """The signature only proves who sent it, never what it says."""
    with pytest.raises(ProviderError, match="сумма"):
        await get_provider("liqpay").verify_webhook(
            headers={}, raw_body=b"", form=liqpay_callback(amount=10.0),
            credentials=LIQPAY_CREDS, amount_minor=99000, invoice_no=4242,
            payment_id=PAYMENT_ID, provider_payment_id=None,
        )


async def test_liqpay_leaves_an_unfinished_payment_alone():
    result = await get_provider("liqpay").verify_webhook(
        headers={}, raw_body=b"", form=liqpay_callback(status="wait_accept"),
        credentials=LIQPAY_CREDS, amount_minor=99000, invoice_no=4242,
        payment_id=PAYMENT_ID, provider_payment_id=None,
    )

    assert result.status.value == "pending"


# --------------------------------------------------------------- Freedom Pay

FREEDOM_CREDS = {"merchant_id": "548469", "secret_key": "freedom_secret"}


def freedom_sign(script: str, params: dict, secret: str = "freedom_secret") -> str:
    parts = [script] + [str(params[k]) for k in sorted(params) if k != "pg_sig"] + [secret]
    return hashlib.md5(";".join(parts).encode()).hexdigest()


async def test_freedompay_signs_the_init_request_and_follows_the_redirect(mock_http):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        from urllib.parse import parse_qsl

        seen.update(dict(parse_qsl(request.content.decode())))
        return httpx.Response(
            200,
            text="<?xml version='1.0'?><response><pg_status>ok</pg_status>"
            "<pg_payment_id>77123</pg_payment_id>"
            "<pg_redirect_url>https://pay.freedompay.money/pay/77123</pg_redirect_url></response>",
        )

    with mock_http(handler):
        checkout = await get_provider("freedompay").create_checkout(
            checkout_request(FREEDOM_CREDS, currency="KZT")
        )

    assert checkout.url == "https://pay.freedompay.money/pay/77123"
    assert checkout.provider_payment_id == "77123"
    assert seen["pg_order_id"] == str(PAYMENT_ID)
    assert seen["pg_amount"] == "990.00"
    # Recomputed from the scheme, not from the adapter's helper.
    assert seen["pg_sig"] == freedom_sign("init_payment.php", seen)


async def test_freedompay_reports_the_gateways_own_refusal(mock_http):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<?xml version='1.0'?><response><pg_status>error</pg_status>"
            "<pg_error_description>Магазин заблокирован</pg_error_description></response>",
        )

    with mock_http(handler), pytest.raises(ProviderError, match="заблокирован"):
        await get_provider("freedompay").create_checkout(checkout_request(FREEDOM_CREDS, currency="KZT"))


async def test_freedompay_callback_is_signed_against_our_own_address():
    """The script name in the signature is the tail of the URL being signed —
    for the callback that is ours, not Freedom Pay's."""
    form = {
        "pg_order_id": str(PAYMENT_ID),
        "pg_payment_id": "77123",
        "pg_result": "1",
        "pg_amount": "990.00",
        "pg_salt": "abc123",
    }
    form["pg_sig"] = freedom_sign("freedompay", form)

    result = await get_provider("freedompay").verify_webhook(
        headers={}, raw_body=b"", form=form, credentials=FREEDOM_CREDS,
        amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID, provider_payment_id=None,
    )

    assert result.status.value == "paid"
    assert "<pg_status>ok</pg_status>" in result.response_body


async def test_freedompay_refuses_a_callback_with_a_swapped_amount():
    form = {
        "pg_order_id": str(PAYMENT_ID),
        "pg_payment_id": "77123",
        "pg_result": "1",
        "pg_amount": "10.00",
        "pg_salt": "abc123",
    }
    form["pg_sig"] = freedom_sign("freedompay", form)

    with pytest.raises(ProviderError, match="сумма"):
        await get_provider("freedompay").verify_webhook(
            headers={}, raw_body=b"", form=form, credentials=FREEDOM_CREDS,
            amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID, provider_payment_id=None,
        )


async def test_freedompay_refuses_an_unsigned_callback():
    with pytest.raises(ProviderError, match="подпись"):
        await get_provider("freedompay").verify_webhook(
            headers={}, raw_body=b"",
            form={"pg_order_id": str(PAYMENT_ID), "pg_result": "1", "pg_amount": "990.00"},
            credentials=FREEDOM_CREDS, amount_minor=99000, invoice_no=4242,
            payment_id=PAYMENT_ID, provider_payment_id=None,
        )


# -------------------------------------------------------------------- Т-Банк

TBANK_CREDS = {"terminal_key": "TinkoffBankTest", "password": "terminal_pass"}


def tbank_token(payload: dict, password: str = "terminal_pass") -> str:
    values = {k: v for k, v in payload.items() if k != "Token" and not isinstance(v, (dict, list))}
    values["Password"] = password
    return hashlib.sha256("".join(str(values[k]) for k in sorted(values)).encode()).hexdigest()


def tbank_api(status: str = "CONFIRMED", amount: int = 99000):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["Token"] == tbank_token(body), "запрос в банк подписан не по схеме"
        if request.url.path.endswith("/Init"):
            return httpx.Response(200, json={
                "Success": True, "PaymentId": "3006574", "PaymentURL": "https://securepayments.tinkoff.ru/x8Kout",
            })
        return httpx.Response(200, json={"Success": True, "Status": status, "Amount": amount})

    return handler


async def test_tbank_signs_init_and_charges_in_kopecks(mock_http):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return tbank_api()(request)

    with mock_http(handler):
        checkout = await get_provider("tbank").create_checkout(checkout_request(TBANK_CREDS))

    assert checkout.url == "https://securepayments.tinkoff.ru/x8Kout"
    assert checkout.provider_payment_id == "3006574"
    assert seen[0]["Amount"] == 99000
    assert seen[0]["OrderId"] == str(PAYMENT_ID)


async def test_tbank_asks_the_bank_rather_than_believing_the_notification(mock_http):
    """A notification body is not proof of anything; GetState is."""
    forged = json.dumps({"OrderId": str(PAYMENT_ID), "PaymentId": "3006574", "Status": "CONFIRMED"}).encode()

    with mock_http(tbank_api(status="REJECTED")):
        result = await get_provider("tbank").verify_webhook(
            headers={}, raw_body=forged, form={}, credentials=TBANK_CREDS,
            amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID, provider_payment_id="3006574",
        )

    assert result.status.value == "failed"


async def test_tbank_settles_only_on_confirmed_not_on_a_hold(mock_http):
    """AUTHORIZED is money held on a two-stage terminal, not money taken."""
    with mock_http(tbank_api(status="AUTHORIZED")):
        held = await get_provider("tbank").check_status(
            credentials=TBANK_CREDS, amount_minor=99000, invoice_no=4242,
            payment_id=PAYMENT_ID, provider_payment_id="3006574", meta={},
        )
    with mock_http(tbank_api(status="CONFIRMED")):
        taken = await get_provider("tbank").check_status(
            credentials=TBANK_CREDS, amount_minor=99000, invoice_no=4242,
            payment_id=PAYMENT_ID, provider_payment_id="3006574", meta={},
        )

    assert held.status.value == "pending"
    assert taken.status.value == "paid"


async def test_tbank_refuses_a_payment_the_bank_says_was_for_less(mock_http):
    with mock_http(tbank_api(amount=1000)), pytest.raises(ProviderError, match="сумма"):
        await get_provider("tbank").check_status(
            credentials=TBANK_CREDS, amount_minor=99000, invoice_no=4242,
            payment_id=PAYMENT_ID, provider_payment_id="3006574", meta={},
        )


# ------------------------------------------------------------- CloudPayments

CP_CREDS = {"public_id": "pk_test", "api_secret": "cp_api_secret"}


def cp_hmac(body: bytes, secret: str = "cp_api_secret") -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def cp_api(status: str = "Completed", amount: float = 990.0):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/orders/create"):
            return httpx.Response(200, json={
                "Success": True,
                "Model": {"Id": "f2K8LV6r", "Url": "https://p.cloudpayments.ru/f2K8LV6r"},
            })
        return httpx.Response(200, json={
            "Success": True,
            "Model": {"TransactionId": 504, "Status": status, "Amount": amount},
        })

    return handler


async def test_cloudpayments_turns_an_invoice_into_a_link(mock_http):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return cp_api()(request)

    with mock_http(handler):
        checkout = await get_provider("cloudpayments").create_checkout(
            checkout_request(CP_CREDS, currency="KZT")
        )

    assert checkout.url == "https://p.cloudpayments.ru/f2K8LV6r"
    assert seen[0]["InvoiceId"] == str(PAYMENT_ID)
    assert seen[0]["Amount"] == 990.0


async def test_cloudpayments_refuses_a_notification_with_a_wrong_hmac(mock_http):
    body = b"TransactionId=504&Amount=990.00&Status=Completed"

    with mock_http(cp_api()), pytest.raises(ProviderError, match="подпись"):
        await get_provider("cloudpayments").verify_webhook(
            headers={"content-hmac": cp_hmac(body, secret="someone_elses")}, raw_body=body,
            form={"InvoiceId": str(PAYMENT_ID)}, credentials=CP_CREDS,
            amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID, provider_payment_id=None,
        )


async def test_cloudpayments_still_re_reads_after_a_valid_hmac(mock_http):
    """A correct HMAC proves the sender; the API says what actually happened,
    and a replayed body must not be able to settle an order on its own."""
    body = b"TransactionId=504&Amount=990.00&Status=Completed"
    headers = {"content-hmac": cp_hmac(body)}

    with mock_http(cp_api(status="Declined")):
        refused = await get_provider("cloudpayments").verify_webhook(
            headers=headers, raw_body=body, form={"InvoiceId": str(PAYMENT_ID)}, credentials=CP_CREDS,
            amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID, provider_payment_id=None,
        )
    with mock_http(cp_api(status="Completed")):
        settled = await get_provider("cloudpayments").verify_webhook(
            headers=headers, raw_body=body, form={"InvoiceId": str(PAYMENT_ID)}, credentials=CP_CREDS,
            amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID, provider_payment_id=None,
        )

    assert refused.status.value == "failed"
    assert settled.status.value == "paid"
    assert settled.response_body == '{"code":0}'  # anything else means "resend"


# --------------------------------------------------------------------- Click

CLICK_CREDS = {"service_id": "12345", "merchant_id": "6789", "secret_key": "click_secret"}


def click_form(action: str, *, amount: str = "990.00", prepare_id: str = "", secret: str = "click_secret"):
    form = {
        "click_trans_id": "2222222",
        "service_id": "12345",
        "merchant_trans_id": "4242",
        "merchant_prepare_id": prepare_id,
        "amount": amount,
        "action": action,
        "sign_time": "2026-09-10 12:00:00",
        "error": "0",
    }
    raw = (
        form["click_trans_id"] + form["service_id"] + secret + form["merchant_trans_id"]
        + form["merchant_prepare_id"] + form["amount"] + form["action"] + form["sign_time"]
    )
    form["sign_string"] = hashlib.md5(raw.encode()).hexdigest()
    return form


async def test_click_prepare_confirms_the_order_without_settling_it():
    result = await get_provider("click").verify_webhook(
        headers={}, raw_body=b"", form=click_form("0"), credentials=CLICK_CREDS,
        amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID, provider_payment_id=None,
    )
    body = json.loads(result.response_body)

    assert result.status.value == "pending", "Prepare — это ещё не деньги"
    assert body["error"] == 0
    # Click repeats this id in Complete, and it goes into that signature.
    assert body["merchant_prepare_id"] == 4242


async def test_click_complete_settles_and_its_signature_includes_the_prepare_id():
    result = await get_provider("click").verify_webhook(
        headers={}, raw_body=b"", form=click_form("1", prepare_id="4242"), credentials=CLICK_CREDS,
        amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID, provider_payment_id=None,
    )

    assert result.status.value == "paid"
    assert json.loads(result.response_body)["error"] == 0


async def test_click_refuses_a_call_signed_with_the_wrong_secret():
    with pytest.raises(ProviderError, match="подпись"):
        await get_provider("click").verify_webhook(
            headers={}, raw_body=b"", form=click_form("1", prepare_id="4242", secret="guessed"),
            credentials=CLICK_CREDS, amount_minor=99000, invoice_no=4242,
            payment_id=PAYMENT_ID, provider_payment_id=None,
        )


async def test_click_refuses_a_correctly_signed_call_for_less_money():
    with pytest.raises(ProviderError, match="сумма"):
        await get_provider("click").verify_webhook(
            headers={}, raw_body=b"", form=click_form("1", amount="10.00", prepare_id="4242"),
            credentials=CLICK_CREDS, amount_minor=99000, invoice_no=4242,
            payment_id=PAYMENT_ID, provider_payment_id=None,
        )


def test_click_answers_a_refusal_in_the_body_not_with_an_http_error():
    """Click reads an HTTP error as a broken integration and retries forever;
    a rejected payment has to come back as 200 with an error code."""
    body, media_type = get_provider("click").error_body(
        form=click_form("1"), raw_body=b"", found=False
    )

    assert media_type == "application/json"
    assert json.loads(body)["error"] == -5


async def test_click_puts_our_invoice_number_in_the_pay_link():
    checkout = await get_provider("click").create_checkout(
        checkout_request(CLICK_CREDS, currency="UZS")
    )

    assert checkout.url.startswith("https://my.click.uz/services/pay?")
    assert "transaction_param=4242" in checkout.url
    assert "service_id=12345" in checkout.url


# --------------------------------------------------------------------- Payme

PAYME_CREDS = {"merchant_id": "5e730e8e0a49f3ed3d1c1cd0", "key": "payme_cash_key"}
PAYME_AUTH = {"authorization": "Basic " + base64.b64encode(b"Paycom:payme_cash_key").decode()}
PAYME_TX = "5e7307d68e2b60b6f2c4dd8b"


def payme_now() -> int:
    """Payme refuses a transaction opened more than 12 hours ago, so the
    tests have to speak in the present tense."""
    import time

    return int(time.time() * 1000)


def payme_call(method: str, params: dict, request_id: int = 1) -> bytes:
    return json.dumps({"method": method, "params": params, "id": request_id}).encode()


async def payme(method: str, params: dict, *, meta: dict | None = None, headers: dict | None = None):
    return await get_provider("payme").verify_webhook(
        headers=PAYME_AUTH if headers is None else headers,
        raw_body=payme_call(method, params), form={}, credentials=PAYME_CREDS,
        amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID,
        provider_payment_id=None, meta=meta or {},
    )


async def test_payme_refuses_everything_without_the_cashbox_key():
    with pytest.raises(ProviderError):
        await payme(
            "CheckPerformTransaction",
            {"amount": 99000, "account": {"order_id": "4242"}},
            headers={"authorization": "Basic " + base64.b64encode(b"Paycom:guessed").decode()},
        )


async def test_payme_refusal_is_a_json_rpc_error_not_an_http_one():
    try:
        await payme(
            "CheckPerformTransaction",
            {"amount": 99000, "account": {"order_id": "4242"}},
            headers={},
        )
    except ProviderError as exc:
        body = json.loads(getattr(exc, "body", "{}"))
        assert body["error"]["code"] == -32504
    else:  # pragma: no cover - the call above must refuse
        pytest.fail("Payme без авторизации должен отказать")


async def test_payme_checks_the_amount_before_allowing_anything():
    allowed = await payme("CheckPerformTransaction", {"amount": 99000, "account": {"order_id": "4242"}})
    assert json.loads(allowed.response_body)["result"] == {"allow": True}

    with pytest.raises(ProviderError) as caught:
        await payme("CheckPerformTransaction", {"amount": 1000, "account": {"order_id": "4242"}})
    assert json.loads(caught.value.body)["error"]["code"] == -31001


async def test_payme_walks_create_then_perform_and_only_then_is_it_paid():
    created = await payme(
        "CreateTransaction",
        {"id": PAYME_TX, "time": payme_now(), "amount": 99000, "account": {"order_id": "4242"}},
    )
    assert created.status.value == "pending", "созданная транзакция — ещё не оплата"
    notes = created.meta["payme"]
    assert notes["state"] == 1

    performed = await payme("PerformTransaction", {"id": PAYME_TX}, meta={"payme": notes})
    assert performed.status.value == "paid"
    assert json.loads(performed.response_body)["result"]["state"] == 2


async def test_payme_repeats_its_own_answer_instead_of_paying_twice():
    """Payme asks again when it does not see an answer, and every reply has
    to carry the same timestamps — a fresh perform_time each time is how a
    single sale becomes two."""
    created = await payme(
        "CreateTransaction",
        {"id": PAYME_TX, "time": payme_now(), "amount": 99000, "account": {"order_id": "4242"}},
    )
    first = await payme("PerformTransaction", {"id": PAYME_TX}, meta={"payme": created.meta["payme"]})
    again = await payme("PerformTransaction", {"id": PAYME_TX}, meta={"payme": first.meta["payme"]})

    assert json.loads(first.response_body)["result"] == json.loads(again.response_body)["result"]
    assert again.meta == {}, "повтор ничего не меняет"


async def test_payme_reports_a_transaction_it_never_created_as_missing():
    with pytest.raises(ProviderError) as caught:
        await payme("PerformTransaction", {"id": "some-other-transaction"}, meta={})
    assert json.loads(caught.value.body)["error"]["code"] == -31003


async def test_payme_will_not_open_a_second_transaction_for_one_order():
    notes = {"id": PAYME_TX, "transaction": PAYME_TX, "create_time": 1_700_000_000_000, "state": 1}

    with pytest.raises(ProviderError) as caught:
        await payme(
            "CreateTransaction",
            {"id": "another-tx", "time": payme_now(), "amount": 99000, "account": {"order_id": "4242"}},
            meta={"payme": notes},
        )
    assert json.loads(caught.value.body)["error"]["code"] == -31008


async def test_payme_cancelling_a_performed_transaction_is_a_refund():
    notes = {
        "id": PAYME_TX, "transaction": PAYME_TX,
        "create_time": 1_700_000_000_000, "perform_time": 1_700_000_100_000, "state": 2,
    }

    cancelled = await payme("CancelTransaction", {"id": PAYME_TX, "reason": 5}, meta={"payme": notes})

    assert cancelled.status.value == "refunded"
    assert json.loads(cancelled.response_body)["result"]["state"] == -2


async def test_payme_check_transaction_reports_what_we_stored():
    notes = {
        "id": PAYME_TX, "transaction": PAYME_TX,
        "create_time": 1_700_000_000_000, "perform_time": 1_700_000_100_000, "state": 2,
    }

    checked = await payme("CheckTransaction", {"id": PAYME_TX}, meta={"payme": notes})
    reported = json.loads(checked.response_body)["result"]

    assert reported["create_time"] == 1_700_000_000_000
    assert reported["perform_time"] == 1_700_000_100_000
    assert reported["cancel_time"] == 0
    assert reported["state"] == 2


async def test_payme_checkout_link_carries_the_cashbox_order_and_amount():
    checkout = await get_provider("payme").create_checkout(
        checkout_request(PAYME_CREDS, currency="UZS", amount_minor=99000)
    )

    assert checkout.url.startswith("https://checkout.paycom.uz/")
    decoded = base64.b64decode(checkout.url.rsplit("/", 1)[1]).decode()
    # Tiyin, the same minor unit everything else is stored in.
    assert "a=99000" in decoded
    assert "ac.order_id=4242" in decoded
    assert f"m={PAYME_CREDS['merchant_id']}" in decoded


async def test_payme_honours_a_cashbox_that_names_its_order_field_differently():
    checkout = await get_provider("payme").create_checkout(
        checkout_request({**PAYME_CREDS, "account_field": "invoice"}, currency="UZS")
    )

    decoded = base64.b64decode(checkout.url.rsplit("/", 1)[1]).decode()
    assert "ac.invoice=4242" in decoded


def test_payme_finds_the_order_by_whatever_the_cashbox_calls_it():
    body = payme_call("CreateTransaction", {"id": PAYME_TX, "account": {"invoice": "4242"}})

    ref = get_provider("payme").locate_payment(headers={}, raw_body=body, form={})

    assert ref.invoice_no == 4242
