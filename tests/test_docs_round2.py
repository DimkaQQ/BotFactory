"""lava.top, ioka и Robokassa по присланной документации (docs/lava-top-api.md, ioka-api.md, robokassa-docs.md)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.models.payment import PaymentStatus
from app.services.payments import get_provider
from app.services.payments.base import CheckoutRequest, ProviderError

PAYMENT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
FIRST = "c5a0cacc-3453-44b0-9532-aa492f1ba191"
RENEWAL = "d41db415-ad71-4f2a-8d8c-27eefee91e66"


def request(creds, *, currency="RUB", is_test=False, extra=None, amount=99000, description="Гайд") -> CheckoutRequest:
    return CheckoutRequest(
        payment_id=PAYMENT_ID, invoice_no=77, amount_minor=amount, currency=currency, description=description,
        return_url="https://t.me/x", is_test=is_test, credentials=creds, extra=extra or {},
    )


# ================================================================== lava.top

LAVA = {"api_key": "k", "buyer_email": "shop@example.com"}


def lava_event(kind, **fields) -> bytes:
    return json.dumps({"eventType": kind, "contractId": fields.pop("contractId", FIRST), **fields}).encode()


def test_lava_renewal_is_located_by_the_parent_contract_not_the_new_one():
    provider = get_provider("lavatop")
    ref = provider.locate_payment(
        headers={}, form={}, raw_body=lava_event("subscription.recurring.payment.success", contractId=RENEWAL, parentContractId=FIRST)
    )
    assert ref.provider_payment_id == FIRST
    first = provider.locate_payment(headers={}, form={}, raw_body=lava_event("payment.success"))
    assert first.provider_payment_id == FIRST


def lava_invoice(status="COMPLETED", amount=990.0):
    def handler(req: httpx.Request) -> httpx.Response:
        if "/subscriptions/" in req.url.path:
            return httpx.Response(200, json={"subscriptionStatus": handler.sub})
        return httpx.Response(200, json={"status": status, "receipt": {"amount": amount, "currency": "RUB"}})

    handler.sub = "ACTIVE"
    return handler


async def lava_verify(mock_http, handler, raw):
    with mock_http(handler):
        return await get_provider("lavatop").verify_webhook(
            headers={}, raw_body=raw, form={}, credentials=LAVA, amount_minor=99000, invoice_no=1,
            payment_id=PAYMENT_ID, provider_payment_id=FIRST, currency="RUB",
        )


async def test_lava_renewal_extends_through_the_gateway_signal_and_keeps_the_first_contract(mock_http):
    raw = lava_event("subscription.recurring.payment.success", contractId=RENEWAL, parentContractId=FIRST)
    result = await lava_verify(mock_http, lava_invoice(), raw)
    assert result.status is PaymentStatus.paid
    assert result.meta == {"gateway_renewal": RENEWAL}
    assert result.provider_payment_id == FIRST, "иначе потеряем контракт, нужный для отмены подписки"


async def test_lava_failed_renewal_never_touches_the_paid_order(mock_http):
    raw = lava_event("subscription.recurring.payment.failed", contractId=RENEWAL, parentContractId=FIRST)
    result = await lava_verify(mock_http, lava_invoice("FAILED"), raw)
    assert result.status is PaymentStatus.pending and not result.meta


async def test_lava_cancellation_is_checked_with_the_api_before_it_cancels_anything(mock_http):
    handler = lava_invoice()
    raw = lava_event("subscription.cancelled", contractId=FIRST)
    assert (await lava_verify(mock_http, handler, raw)).meta == {}, "по телу уведомления не отменяем"
    handler.sub = "CANCELLED"
    assert (await lava_verify(mock_http, handler, raw)).meta == {"gateway_unsubscribed": True}


async def test_lava_checks_the_block_price_against_the_catalogue(monkeypatch):
    from app.services.payments import lavatop

    async def prices(api_key):
        return [{"offer_id": "o1", "product": "P", "currency": "RUB", "amount": 990.5, "periodicity": "ONE_TIME"}]

    monkeypatch.setattr(lavatop, "offer_prices", prices)
    provider = get_provider("lavatop")
    await provider._check_offer_price(LAVA, "o1", "RUB", "ONE_TIME", 99050)
    with pytest.raises(ProviderError, match="оффер стоит 990.5"):
        await provider._check_offer_price(LAVA, "o1", "RUB", "ONE_TIME", 99000)


async def test_lava_finds_the_offer_from_a_product_id_or_the_product_page_link():
    from app.services.payments.lavatop import resolve_offer_id

    product = "843f7652-0494-41cb-b035-62f39380576a"
    offer = "11111111-2222-3333-4444-555555555555"
    prices = [
        {"product_id": product, "offer_id": offer, "product": "P", "currency": "RUB", "amount": 990.0,
         "periodicity": "ONE_TIME"},
    ]
    # offerId остаётся offerId, id товара и ссылка со страницы товара превращаются в оффер.
    assert resolve_offer_id(offer, prices, "RUB", "ONE_TIME") == offer
    assert resolve_offer_id(product, prices, "RUB", "ONE_TIME") == offer
    assert resolve_offer_id(f"https://app.lava.top/products/{product.upper()}/content", prices, "RUB", "ONE_TIME") == offer
    # Нет каталога — ничего не угадываем, вставленное идёт дальше как есть.
    assert resolve_offer_id(product, [], "RUB", "ONE_TIME") == product
    # У товара нет оффера с такой валютой/периодом — говорим, что есть.
    with pytest.raises(ProviderError, match="RUB/ONE_TIME|нет оффера"):
        resolve_offer_id(product, prices, "USD", "ONE_TIME")


async def test_lava_asks_for_the_offer_id_when_a_product_has_several_matching_offers():
    from app.services.payments.lavatop import resolve_offer_id

    product = "843f7652-0494-41cb-b035-62f39380576a"
    prices = [
        {"product_id": product, "offer_id": f"o{n}", "product": "P", "currency": "RUB", "amount": 100.0,
         "periodicity": "ONE_TIME"}
        for n in (1, 2)
    ]
    with pytest.raises(ProviderError, match="несколько офферов"):
        resolve_offer_id(product, prices, "RUB", "ONE_TIME")


async def test_lava_catalogue_asks_for_hidden_products_and_follows_the_pages():
    """Товар, который продаётся только по ссылке, скрыт, а по умолчанию lava.top отдаёт лишь видимые;
    лента к тому же постраничная — оффер со второй страницы тоже должен найтись."""
    from app.services.payments import lavatop

    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        if "beforeCreatedAt" in str(request.url):
            body = {"items": [{"type": "PRODUCT", "data": {"id": "p2", "title": "Второй", "offers": [
                {"id": "o2", "prices": [{"currency": "RUB", "amount": 50, "periodicity": "ONE_TIME"}]}]}}],
                    "nextPage": None}
        else:
            body = {"items": [{"type": "PRODUCT", "data": {"id": "p1", "title": "Первый", "offers": [
                {"id": "o1", "prices": [{"currency": "RUB", "amount": 10, "periodicity": "ONE_TIME"}]}]}}],
                    "nextPage": "https://gate.lava.top/api/v2/products?beforeCreatedAt=2026-01-01T00:00:00Z"}
        return httpx.Response(200, json=body)

    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    import unittest.mock as mock

    with mock.patch.object(lavatop.httpx, "AsyncClient", client_factory):
        prices = await lavatop.offer_prices("key")

    assert seen[0].params["feedVisibility"] == "ALL"
    assert {p["offer_id"] for p in prices} == {"o1", "o2"}
    assert {p["product_id"] for p in prices} == {"p1", "p2"}


# ===================================================================== ioka

IOKA = {"client_id": "cid", "client_secret": "sec"}


def ioka_api(log, *, expiry_in=3600, unauthorized_once=False, hooks=None, refunded=0):
    state = {"token_calls": 0, "n": 0, "unauth": unauthorized_once}

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        log.append((req.method, path, dict(req.headers).get("api-key")))
        if path.endswith("/auth/token"):
            state["token_calls"] += 1
            expires = (datetime.now(timezone.utc) + timedelta(seconds=expiry_in)).isoformat()
            return httpx.Response(200, json={"api_key": f"key{state['token_calls']}", "expiry_date": expires})
        if state["unauth"] and path.endswith("/orders") and req.method == "POST":
            state["unauth"] = False
            return httpx.Response(401, json={"message": "expired"})
        if path.endswith("/webhooks"):
            return httpx.Response(200, json=hooks or []) if req.method == "GET" else httpx.Response(201, json={"id": "w1"})
        if path.endswith("/payments"):
            return httpx.Response(200, json=[{"id": "p1", "refunded_amount": refunded, "captured_amount": 99000}])
        order = {"id": "ord1", "status": "PAID", "amount": 99000, "currency": "KZT", "checkout_url": "https://pay/ord1"}
        return httpx.Response(201 if req.method == "POST" else 200, json=order)

    handler.state = state
    return handler


async def test_ioka_gets_its_api_key_from_client_credentials_and_caches_it(mock_http):
    log: list = []
    handler = ioka_api(log)
    provider = get_provider("ioka")
    with mock_http(handler):
        await provider.create_checkout(request(IOKA, currency="KZT", is_test=True))
        await provider.create_checkout(request(IOKA, currency="KZT", is_test=True))
    assert handler.state["token_calls"] == 1, "ключ живёт до истечения срока, незачем просить его каждый раз"
    orders = [e for e in log if e[1].endswith("/orders")]
    assert orders and all(e[2] == "key1" for e in orders)


async def test_ioka_renews_an_expired_key_and_retries_once_on_401(mock_http):
    log: list = []
    handler = ioka_api(log, unauthorized_once=True)
    with mock_http(handler):
        checkout = await get_provider("ioka").create_checkout(request(IOKA, currency="KZT", is_test=True))
    assert checkout.provider_payment_id == "ord1"
    assert handler.state["token_calls"] == 2, "после 401 берём новый ключ"

    log2: list = []
    short = ioka_api(log2, expiry_in=10)  # живёт меньше минуты — считаем истёкшим
    with mock_http(short):
        await get_provider("ioka").create_checkout(request({"client_id": "other", "client_secret": "s"}, currency="KZT", is_test=True))
        await get_provider("ioka").create_checkout(request({"client_id": "other", "client_secret": "s"}, currency="KZT", is_test=True))
    assert short.state["token_calls"] >= 2


async def test_ioka_takes_only_tenge():
    with pytest.raises(ProviderError, match="только тенге"):
        await get_provider("ioka").create_checkout(request(IOKA, currency="RUB"))
    assert get_provider("ioka").currencies == ("KZT",)


async def test_ioka_registers_our_webhook_once_and_leaves_foreign_ones_alone(mock_http):
    log: list = []
    with mock_http(ioka_api(log)):
        await get_provider("ioka").create_checkout(request(IOKA, currency="KZT", is_test=True))
    assert ("POST", "/v2/webhooks") in [(m, p) for m, p, _ in log]

    from app.services.payments.ioka import IokaProvider

    IokaProvider._webhooks_ready.clear()
    log2: list = []
    ours = f"{__import__('app.config', fromlist=['x']).get_settings().public_base_url.rstrip('/')}/webhook/pay/ioka"
    with mock_http(ioka_api(log2, hooks=[{"id": "w0", "url": ours, "events": []}])):
        await get_provider("ioka").create_checkout(request(IOKA, currency="KZT", is_test=True))
    assert ("POST", "/v2/webhooks") not in [(m, p) for m, p, _ in log2], "уже есть — не дублируем"


async def ioka_verify(mock_http, handler, event):
    raw = json.dumps({"event": event, "order": {"external_id": str(PAYMENT_ID)}}).encode()
    with mock_http(handler):
        return await get_provider("ioka").verify_webhook(
            headers={}, raw_body=raw, form={}, credentials=IOKA, amount_minor=99000, invoice_no=1,
            payment_id=PAYMENT_ID, provider_payment_id="ord1", meta={"is_test": True}, currency="KZT",
        )


async def test_ioka_sees_a_full_refund_in_the_payments_not_in_the_order_status(mock_http):
    assert (await ioka_verify(mock_http, ioka_api([], refunded=99000), "REFUND_APPROVED")).status is PaymentStatus.refunded
    partial = await ioka_verify(mock_http, ioka_api([], refunded=10000), "REFUND_APPROVED")
    assert partial.status is PaymentStatus.paid, "частичный возврат заказ не закрывает"
    plain = await ioka_verify(mock_http, ioka_api([], refunded=99000), "PAYMENT_CAPTURED")
    assert plain.status is PaymentStatus.paid, "без события возврата платежи не читаем"


def test_ioka_acknowledges_events_about_orders_that_are_not_ours():
    provider = get_provider("ioka")
    assert provider.error_body(form={}, raw_body=b"{}", found=False) == ("{}", "application/json")
    assert provider.error_body(form={}, raw_body=b"{}", found=True) is None


# ================================================================== Robokassa

ROBO = {"merchant_login": "shop", "password1": "p1", "password2": "p2"}


async def test_robokassa_signs_with_the_algorithm_chosen_in_the_shop_settings():
    sha = {**ROBO, "hash_algo": "sha256"}
    checkout = await get_provider("robokassa").create_checkout(request({**sha, "test_password1": "t1"}, is_test=True))
    query = parse_qs(urlsplit(checkout.url).query)
    assert query["SignatureValue"][0] == hashlib.sha256(b"shop:990.00:77:t1").hexdigest()

    with pytest.raises(ProviderError, match="алгоритм"):
        await get_provider("robokassa").create_checkout(request({**ROBO, "hash_algo": "crc32"}))


async def result_url(form, creds):
    return await get_provider("robokassa").verify_webhook(
        headers={}, raw_body=b"", form=form, credentials=creds, amount_minor=99000, invoice_no=77,
        payment_id=PAYMENT_ID, provider_payment_id=None, meta={"robokassa_test": False},
    )


async def test_robokassa_result_url_uses_the_same_algorithm_and_counts_shp_parameters():
    creds = {**ROBO, "hash_algo": "sha256"}
    base = "990.000000:77:p2:Shp_a=1:Shp_b=2"
    form = {"OutSum": "990.000000", "InvId": "77", "Shp_b": "2", "Shp_a": "1",
            "SignatureValue": hashlib.sha256(base.encode()).hexdigest().upper()}
    assert (await result_url(form, creds)).response_body == "OK77"

    with pytest.raises(ProviderError, match="подпись"):
        await result_url({**form, "Shp_a": "tampered"}, creds)
    with pytest.raises(ProviderError, match="подпись"):
        await result_url(form, ROBO)  # md5 по умолчанию — подпись sha256 не подходит


async def test_robokassa_description_has_no_special_characters_and_is_short():
    checkout = await get_provider("robokassa").create_checkout(request(ROBO, description='Бот "Магазин" & <Co> %' + "я" * 200))
    description = parse_qs(urlsplit(checkout.url).query)["Description"][0]
    assert len(description) <= 100 and not any(ch in description for ch in '"&<>%')


async def test_freedompay_has_a_host_per_country():
    from app.services.payments.freedompay import FreedomPayProvider

    base = FreedomPayProvider._base
    assert base({}) == "https://api.freedompay.kz"
    assert base({"country": "uz"}) == "https://api.freedompay.uz"
    assert base({"country": "KG"}) == "https://api.freedompay.kg"


# ===================================================== Freedom Pay: Gateway API

FP = {"merchant_id": "548469", "secret_key": "fp_secret"}


def fp_xml(**fields) -> str:
    return "<?xml version='1.0' encoding='utf-8'?><response>" + "".join(f"<{k}>{v}</{k}>" for k, v in fields.items()) + "</response>"


def fp_api(log, *, state="success", captured="1", amount="990", refunded="0", status_error=None):
    def handler(req: httpx.Request) -> httpx.Response:
        body = dict(x.split("=", 1) for x in req.content.decode().split("&")) if req.content else {}
        log.append((req.url.path, body))
        name = req.url.path.rsplit("/", 1)[-1]
        if name == "status_v2":
            if status_error:
                return httpx.Response(200, text=fp_xml(pg_status="error", pg_error_code=status_error, pg_error_description="x"))
            return httpx.Response(200, text=fp_xml(
                pg_status="ok", pg_payment_status=state, pg_amount=amount, pg_currency="KZT", pg_captured=captured,
                pg_refund_amount=refunded, pg_failure_description="Недостаточно средств" if state == "error" else "",
            ))
        if name == "clearing":
            return httpx.Response(200, text=fp_xml(pg_status="ok"))
        if name == "recurrent":
            return httpx.Response(200, text=fp_xml(pg_status="ok", pg_payment_id="555", pg_recurring_profile="60144557"))
        return httpx.Response(200, text=fp_xml(pg_status="ok", pg_payment_id="555", pg_redirect_url="https://pay"))

    return handler


async def fp_check(mock_http, handler, **kwargs):
    with mock_http(handler):
        return await get_provider("freedompay").check_status(
            credentials=FP, amount_minor=99000, invoice_no=1, payment_id=PAYMENT_ID, provider_payment_id="555",
            meta={"freedompay_order_id": PAYMENT_ID.hex}, currency="KZT", **kwargs,
        )


async def test_freedompay_reads_the_payment_status_with_a_signed_status_v2_call(mock_http):
    log: list = []
    result = await fp_check(mock_http, fp_api(log))
    assert result.status is PaymentStatus.paid
    path, body = log[0]
    assert path == "/g2g/status_v2" and body["pg_order_id"] == PAYMENT_ID.hex and body["pg_payment_id"] == "555"
    signed = {k: v for k, v in body.items() if k != "pg_sig"}
    base = ";".join(["status_v2", *[signed[k] for k in sorted(signed)], "fp_secret"])
    assert body["pg_sig"] == hashlib.md5(base.encode()).hexdigest()


async def test_freedompay_statuses_map_to_ours(mock_http):
    assert (await fp_check(mock_http, fp_api([], state="pending"))).status is PaymentStatus.pending
    failed = await fp_check(mock_http, fp_api([], state="error"))
    assert failed.status is PaymentStatus.failed and "Недостаточно" in failed.meta["decline"]
    assert (await fp_check(mock_http, fp_api([], status_error="11068"))).status is PaymentStatus.pending, "платёж ещё не создан"
    assert (await fp_check(mock_http, fp_api([], refunded="990"))).status is PaymentStatus.refunded
    assert (await fp_check(mock_http, fp_api([], refunded="100"))).status is PaymentStatus.paid, "частичный возврат заказ не закрывает"
    with pytest.raises(ProviderError, match="сумма"):
        await fp_check(mock_http, fp_api([], amount="10"))


async def test_freedompay_clears_a_held_two_step_payment(mock_http):
    log: list = []
    result = await fp_check(mock_http, fp_api(log, captured="0"))
    assert result.status is PaymentStatus.paid
    assert [p for p, _ in log] == ["/g2g/status_v2", "/g2g/clearing"]


async def test_freedompay_renewal_reads_its_result_right_away(mock_http):
    from app.services.payments.base import RecurringSetup

    log: list = []
    with mock_http(fp_api(log)):
        verdict = await get_provider("freedompay").charge_recurring(
            credentials=FP, setup=RecurringSetup(token="60144557"), amount_minor=99000, currency="KZT",
            description="Клуб", payment_id=PAYMENT_ID, invoice_no=9,
        )
    assert [p for p, _ in log] == ["/g2g/recurrent", "/g2g/status_v2"]
    assert verdict.status is PaymentStatus.paid and verdict.provider_payment_id == "555"

    log2: list = []
    with mock_http(fp_api(log2, state="error")):
        declined = await get_provider("freedompay").charge_recurring(
            credentials=FP, setup=RecurringSetup(token="60144557"), amount_minor=99000, currency="KZT",
            description="Клуб", payment_id=PAYMENT_ID, invoice_no=9,
        )
    assert declined.status is PaymentStatus.failed


# ============================================================ Robokassa: OpStateExt


def robo_state(code="100", result="0", out_sum="990.000000"):
    def handler(req: httpx.Request) -> httpx.Response:
        handler.seen = req
        return httpx.Response(200, text=(
            '<OperationStateResponse xmlns="http://merchant.roboxchange.com/WebService/">'
            f"<Result><Code>{result}</Code></Result><State><Code>{code}</Code></State>"
            f"<Info><OutSum>{out_sum}</OutSum></Info></OperationStateResponse>"
        ))

    return handler


async def robo_check(mock_http, handler, meta=None):
    with mock_http(handler):
        return await get_provider("robokassa").check_status(
            credentials=ROBO, amount_minor=99000, invoice_no=77, payment_id=PAYMENT_ID,
            provider_payment_id="77", meta=meta or {}, currency="RUB",
        )


async def test_robokassa_asks_opstateext_with_a_password2_signature(mock_http):
    handler = robo_state()
    result = await robo_check(mock_http, handler)
    assert result.status is PaymentStatus.paid
    query = parse_qs(urlsplit(str(handler.seen.url)).query)
    assert query["Signature"][0] == hashlib.md5(b"shop:77:p2").hexdigest()
    assert query["InvoiceID"] == ["77"] and "OpStateExt" in handler.seen.url.path


async def test_robokassa_operation_states_map_to_ours(mock_http):
    for code, expected in (("10", PaymentStatus.failed), ("60", PaymentStatus.refunded), ("5", PaymentStatus.pending),
                           ("50", PaymentStatus.pending), ("20", PaymentStatus.pending), ("80", PaymentStatus.pending)):
        assert (await robo_check(mock_http, robo_state(code))).status is expected, code
    assert (await robo_check(mock_http, robo_state(result="3"))).status is PaymentStatus.pending, "операции ещё нет"
    with pytest.raises(ProviderError, match="код 1"):
        await robo_check(mock_http, robo_state(result="1"))
    with pytest.raises(ProviderError, match="сумма"):
        await robo_check(mock_http, robo_state(out_sum="10"))
    with pytest.raises(ProviderError, match="тестового"):
        await robo_check(mock_http, robo_state(), meta={"robokassa_test": True})


async def test_robokassa_renewal_carries_the_receipt_inside_the_signature(mock_http):
    from app.services.payments.base import RecurringSetup

    seen = {}

    def handler(req):
        seen["body"] = parse_qs(req.content.decode())
        return httpx.Response(200, text="OK156")

    creds = {**ROBO, "fiscalization_enabled": "1", "fiscal_email": "shop@example.com", "default_vat": "vat22"}
    with mock_http(handler):
        await get_provider("robokassa").charge_recurring(
            credentials=creds, setup=RecurringSetup(token="154"), amount_minor=99000, currency="RUB",
            description="Клуб", payment_id=PAYMENT_ID, invoice_no=156,
        )
    body = seen["body"]
    receipt_once = body["Receipt"][0]
    assert body["SignatureValue"][0] == hashlib.md5(f"shop:990.00:156:{receipt_once}:p1".encode()).hexdigest()
    assert body["PreviousInvoiceID"] == ["154"] and body["InvoiceID"] == ["156"]


# ================================================================ lava.top: return URLs


async def test_lava_leaves_out_return_urls_it_would_reject(mock_http):
    seen = []

    def handler(req):
        if req.method == "POST":
            seen.append(json.loads(req.content))
        return httpx.Response(201, json={"id": FIRST, "paymentUrl": "https://pay", "amountTotal": {"amount": 990}})

    provider = get_provider("lavatop")
    with mock_http(handler):
        await provider.create_checkout(request({**LAVA}, extra={"offer_id": "o1"}, amount=99000))
        bad = CheckoutRequest(
            payment_id=PAYMENT_ID, invoice_no=1, amount_minor=99000, currency="RUB", description="x",
            return_url="http://insecure.example/x", is_test=False, credentials=LAVA, extra={"offer_id": "o1"},
        )
        await provider.create_checkout(bad)
    assert seen[0]["successful_return_url"] == "https://t.me/x"
    assert "successful_return_url" not in seen[1], "http-адрес lava.top отверг бы весь счёт"


# ------------------------------------------------ ЮKassa по официальному OpenAPI


def test_yookassa_receipt_phone_digits_only_and_quantity_number():
    from decimal import Decimal

    from app.services.payments.base import Receipt, ReceiptItem, TaxSystem, Vat
    from app.services.payments.yookassa import receipt_yookassa

    body = receipt_yookassa(
        Receipt(items=[ReceiptItem(name="Гайд", qty=Decimal(1), price=Decimal("990.00"), vat=Vat.NONE)], tax_system=TaxSystem.USN_INCOME, phone="+79000000000")
    )
    assert body["customer"] == {"phone": "79000000000"}
    assert body["items"][0]["quantity"] == 1.0


def test_yookassa_refund_event_is_located_by_payment_id():
    from app.services.payments import get_provider

    raw = json.dumps(
        {"event": "refund.succeeded", "object": {"id": "refund-1", "payment_id": "pay-777", "status": "succeeded"}}
    ).encode()
    ref = get_provider("yookassa").locate_payment(headers={}, raw_body=raw, form={})
    assert ref.provider_payment_id == "pay-777"


def test_yookassa_tax_system_code_is_validated():
    import pytest

    from app.services.payments.base import ProviderError
    from app.services.payments.yookassa import _tax_system

    assert _tax_system({}) is None
    assert _tax_system({"tax_system_code": "2"}) == 2
    with pytest.raises(ProviderError):
        _tax_system({"tax_system_code": "9"})


async def test_yookassa_partial_refund_keeps_payment_paid(mock_http):
    from app.models.payment import PaymentStatus
    from app.services.payments import get_provider

    def api(refunded: str):
        def handler(request):
            return httpx.Response(200, json={
                "id": "p1", "status": "succeeded", "paid": True,
                "amount": {"value": "990.00", "currency": "RUB"},
                "refunded_amount": {"value": refunded, "currency": "RUB"}})
        return handler

    creds = {"shop_id": "1", "secret_key": "s"}
    kwargs = dict(credentials=creds, amount_minor=99000, invoice_no=1, payment_id=PAYMENT_ID, provider_payment_id="p1", meta={}, currency="RUB")
    with mock_http(api("100.00")):
        assert (await get_provider("yookassa").check_status(**kwargs)).status == PaymentStatus.paid
    with mock_http(api("990.00")):
        assert (await get_provider("yookassa").check_status(**kwargs)).status == PaymentStatus.refunded
