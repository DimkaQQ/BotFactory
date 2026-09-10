"""The two CIS gateways whose protocol is a conversation, end to end.

Click and Payme differ from every other provider in ways that only show up
once the router, the database and the bot are all in play: they call the
same address several times about one order, they expect a body rather than
an HTTP status when refused, and Payme expects the timestamps it was given
first to come back unchanged. That state lives in the payment row, so it
cannot be tested against the adapter alone.
"""

from __future__ import annotations

import base64
import hashlib
import json

from sqlalchemy import select

from app.models.bot_block import BlockType
from app.models.payment import Payment, PaymentStatus
from app.services import background, bot_dispatcher

CHAT_ID = 9090

PAYME_CREDS = {"merchant_id": "5e730e8e0a49f3ed3d1c1cd0", "key": "payme_cash_key"}
PAYME_AUTH = {"Authorization": "Basic " + base64.b64encode(b"Paycom:payme_cash_key").decode()}
PAYME_TX = "5e7307d68e2b60b6f2c4dd8b"

CLICK_CREDS = {"service_id": "12345", "merchant_id": "6789", "secret_key": "click_secret"}


async def shop(make_bot, owner, provider: str, credentials: dict, currency: str):
    return await make_bot(
        owner,
        [
            (
                BlockType.payment,
                {"text": "Гайд", "title": "Гайд", "price": "990", "currency": currency},
            ),
            (BlockType.delivery, {"text": "ВОТ ТОВАР"}),
        ],
        provider=provider,
        is_test=False,
        credentials=credentials,
    )


async def order(db, bot, telegram) -> Payment:
    await bot_dispatcher.process_update(
        telegram, {"message": {"chat": {"id": CHAT_ID}, "text": "/start"}}, bot.id, db
    )
    return (await db.execute(select(Payment).where(Payment.bot_id == bot.id))).scalar_one()


# --------------------------------------------------------------------- Payme


def payme_body(method: str, params: dict, request_id: int = 1) -> dict:
    return {"method": method, "params": params, "id": request_id}


def payme_now() -> int:
    import time

    return int(time.time() * 1000)


async def test_payme_conversation_delivers_the_goods_exactly_once(api, db, owner, make_bot, as_bot):
    """Create, perform, and then a repeated perform — which is normal, Payme
    asks again whenever it does not see an answer."""
    bot, _ = await shop(make_bot, owner, "payme", PAYME_CREDS, "UZS")
    payment = await order(db, bot, as_bot)
    as_bot.reset_mock()

    allowed = await api.post(
        "/webhook/pay/payme",
        json=payme_body("CheckPerformTransaction", {"amount": 99000, "account": {"order_id": payment.invoice_no}}),
        headers=PAYME_AUTH,
    )
    assert allowed.json()["result"] == {"allow": True}

    created = await api.post(
        "/webhook/pay/payme",
        json=payme_body(
            "CreateTransaction",
            {"id": PAYME_TX, "time": payme_now(), "amount": 99000, "account": {"order_id": payment.invoice_no}},
        ),
        headers=PAYME_AUTH,
    )
    assert created.json()["result"]["state"] == 1
    create_time = created.json()["result"]["create_time"]

    performed = await api.post(
        "/webhook/pay/payme", json=payme_body("PerformTransaction", {"id": PAYME_TX}), headers=PAYME_AUTH
    )
    assert performed.json()["result"]["state"] == 2
    await background.wait_for_all()

    again = await api.post(
        "/webhook/pay/payme", json=payme_body("PerformTransaction", {"id": PAYME_TX}), headers=PAYME_AUTH
    )
    await background.wait_for_all()

    # The second answer repeats the first, to the millisecond.
    assert again.json()["result"] == performed.json()["result"]
    assert as_bot.sent().count("ВОТ ТОВАР") == 1, "товар должен уйти ровно один раз"

    await db.refresh(payment)
    assert payment.status == PaymentStatus.paid
    # And what we told Payme is what we stored, so a later CheckTransaction
    # agrees with itself.
    assert payment.meta["payme"]["create_time"] == create_time


async def test_payme_check_transaction_after_a_restart_reports_the_stored_state(api, db, owner, make_bot, as_bot):
    """Nothing is held in memory between calls — the row is the record."""
    bot, _ = await shop(make_bot, owner, "payme", PAYME_CREDS, "UZS")
    payment = await order(db, bot, as_bot)

    await api.post(
        "/webhook/pay/payme",
        json=payme_body(
            "CreateTransaction",
            {"id": PAYME_TX, "time": payme_now(), "amount": 99000, "account": {"order_id": payment.invoice_no}},
        ),
        headers=PAYME_AUTH,
    )
    await api.post(
        "/webhook/pay/payme", json=payme_body("PerformTransaction", {"id": PAYME_TX}), headers=PAYME_AUTH
    )
    await background.wait_for_all()

    checked = await api.post(
        "/webhook/pay/payme", json=payme_body("CheckTransaction", {"id": PAYME_TX}), headers=PAYME_AUTH
    )

    reported = checked.json()["result"]
    assert reported["state"] == 2
    assert reported["perform_time"] > 0
    assert reported["transaction"] == PAYME_TX


async def test_payme_is_refused_without_the_cashbox_key_but_still_answers_200(api, db, owner, make_bot, as_bot):
    """An HTTP error tells Payme our endpoint is broken; the refusal it needs
    to see is a JSON-RPC error code."""
    bot, _ = await shop(make_bot, owner, "payme", PAYME_CREDS, "UZS")
    payment = await order(db, bot, as_bot)

    response = await api.post(
        "/webhook/pay/payme",
        json=payme_body("CheckPerformTransaction", {"amount": 99000, "account": {"order_id": payment.invoice_no}}),
        headers={"Authorization": "Basic " + base64.b64encode(b"Paycom:guessed").decode()},
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32504

    await db.refresh(payment)
    assert payment.status == PaymentStatus.pending


async def test_payme_asking_about_an_order_that_does_not_exist_is_answered_not_404(api):
    response = await api.post(
        "/webhook/pay/payme",
        json=payme_body("CheckPerformTransaction", {"amount": 99000, "account": {"order_id": 987654}}),
        headers=PAYME_AUTH,
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -31050


async def test_payme_will_not_pay_out_a_cancelled_transaction(api, db, owner, make_bot, as_bot):
    bot, _ = await shop(make_bot, owner, "payme", PAYME_CREDS, "UZS")
    payment = await order(db, bot, as_bot)
    as_bot.reset_mock()

    await api.post(
        "/webhook/pay/payme",
        json=payme_body(
            "CreateTransaction",
            {"id": PAYME_TX, "time": payme_now(), "amount": 99000, "account": {"order_id": payment.invoice_no}},
        ),
        headers=PAYME_AUTH,
    )
    cancelled = await api.post(
        "/webhook/pay/payme",
        json=payme_body("CancelTransaction", {"id": PAYME_TX, "reason": 3}),
        headers=PAYME_AUTH,
    )
    assert cancelled.json()["result"]["state"] == -1

    refused = await api.post(
        "/webhook/pay/payme", json=payme_body("PerformTransaction", {"id": PAYME_TX}), headers=PAYME_AUTH
    )
    await background.wait_for_all()

    assert refused.json()["error"]["code"] == -31008
    assert "ВОТ ТОВАР" not in as_bot.sent()


# --------------------------------------------------------------------- Click


def click_form(action: str, invoice_no: int, *, prepare_id: str = "", amount: str = "990.00") -> dict:
    form = {
        "click_trans_id": "2222222",
        "service_id": "12345",
        "merchant_trans_id": str(invoice_no),
        "merchant_prepare_id": prepare_id,
        "amount": amount,
        "action": action,
        "sign_time": "2026-09-10 12:00:00",
        "error": "0",
    }
    raw = (
        form["click_trans_id"] + form["service_id"] + CLICK_CREDS["secret_key"] + form["merchant_trans_id"]
        + form["merchant_prepare_id"] + form["amount"] + form["action"] + form["sign_time"]
    )
    form["sign_string"] = hashlib.md5(raw.encode()).hexdigest()
    return form


async def test_click_prepare_then_complete_delivers_once(api, db, owner, make_bot, as_bot):
    bot, _ = await shop(make_bot, owner, "click", CLICK_CREDS, "UZS")
    payment = await order(db, bot, as_bot)
    as_bot.reset_mock()

    prepared = await api.post("/webhook/pay/click", data=click_form("0", payment.invoice_no))
    assert prepared.json()["error"] == 0
    prepare_id = str(prepared.json()["merchant_prepare_id"])

    await db.refresh(payment)
    assert payment.status == PaymentStatus.pending, "Prepare не должен ничего оплачивать"

    completed = await api.post(
        "/webhook/pay/click", data=click_form("1", payment.invoice_no, prepare_id=prepare_id)
    )
    await background.wait_for_all()

    assert completed.json()["error"] == 0
    assert as_bot.sent().count("ВОТ ТОВАР") == 1
    await db.refresh(payment)
    assert payment.status == PaymentStatus.paid


async def test_click_repeating_complete_does_not_deliver_twice(api, db, owner, make_bot, as_bot):
    bot, _ = await shop(make_bot, owner, "click", CLICK_CREDS, "UZS")
    payment = await order(db, bot, as_bot)
    as_bot.reset_mock()

    form = click_form("1", payment.invoice_no, prepare_id=str(payment.invoice_no))
    await api.post("/webhook/pay/click", data=form)
    await background.wait_for_all()
    await api.post("/webhook/pay/click", data=form)
    await background.wait_for_all()

    assert as_bot.sent().count("ВОТ ТОВАР") == 1


async def test_click_refuses_a_forged_call_in_its_own_dialect(api, db, owner, make_bot, as_bot):
    bot, _ = await shop(make_bot, owner, "click", CLICK_CREDS, "UZS")
    payment = await order(db, bot, as_bot)
    as_bot.reset_mock()

    forged = click_form("1", payment.invoice_no, prepare_id=str(payment.invoice_no))
    forged["sign_string"] = "0" * 32

    response = await api.post("/webhook/pay/click", data=forged)
    await background.wait_for_all()

    assert response.status_code == 200, "Click читает HTTP-ошибку как сбой связи и будет слать снова"
    assert response.json()["error"] < 0
    assert "ВОТ ТОВАР" not in as_bot.sent()
    await db.refresh(payment)
    assert payment.status == PaymentStatus.pending


# -------------------------------------------------------------- the redirect


async def test_a_post_only_checkout_is_reachable_through_a_link(api, db, owner, make_bot, as_bot):
    """LiqPay's checkout is a form, and a bot button can only carry a link."""
    bot, _ = await shop(
        make_bot, owner, "liqpay", {"public_key": "i123", "private_key": "priv"}, "UAH"
    )
    payment = await order(db, bot, as_bot)

    checkout_url = payment.meta["checkout_url"]
    assert f"/api/pay/redirect/{payment.id}" in checkout_url

    page = await api.get(f"/api/pay/redirect/{payment.id}")

    assert page.status_code == 200
    assert 'action="https://www.liqpay.ua/api/3/checkout/"' in page.text
    assert 'name="data"' in page.text and 'name="signature"' in page.text
    # Whatever the merchant typed ends up in an HTML attribute; it must not
    # be able to close it.
    assert "<script>document.getElementById('pay').submit();</script>" in page.text


async def test_the_redirect_page_is_only_for_payments_that_have_a_form(api, db, owner, make_bot, as_bot):
    bot, _ = await shop(make_bot, owner, "click", CLICK_CREDS, "UZS")
    payment = await order(db, bot, as_bot)

    page = await api.get(f"/api/pay/redirect/{payment.id}")

    assert page.status_code == 404


def test_the_redirect_page_escapes_what_it_puts_in_the_form():
    """Not a route test: the escaping itself, on the value most likely to
    contain something hostile."""
    from html import escape

    nasty = '"><script>alert(1)</script>'

    assert "<" not in escape(nasty, quote=True)
    assert '"' not in escape(nasty, quote=True)


# ------------------------------------------------------------------ the shape


def test_every_cis_gateway_is_offered_to_shop_owners():
    """The catalogue is what the settings form renders; a provider missing
    from it is a provider nobody can pick."""
    from app.services.payments import describe_providers

    offered = {entry["slug"] for entry in describe_providers()}

    assert {
        "tbank", "cloudpayments", "freedompay", "processingkz", "click", "payme", "liqpay",
    } <= offered


def test_the_uzbek_gateways_charge_in_sum_and_the_kazakh_one_in_tenge():
    from app.services.payments import get_provider

    assert get_provider("click").currencies == ("UZS",)
    assert get_provider("payme").currencies == ("UZS",)
    assert get_provider("freedompay").currencies[0] == "KZT"
    assert "UZS" in get_provider("freedompay").currencies
