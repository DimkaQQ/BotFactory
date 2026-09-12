"""The provider adapters, on their own — no database, no bot.

Two families are covered, and the distinction is the whole point:

* **signature providers** (Prodamus, Robokassa, Stripe) prove a callback is
  genuine by cryptography, so the tests recompute the signature independently
  and check that tampering is refused;
* **API providers** (ЮKassa, PayMaster, LIFE PAY, lava.top) sign nothing, so
  the tests check the request we send *and* that a lying callback changes
  nothing because the provider's own API is asked.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import httpx
import pytest

from app.services.payments import get_provider
from app.services.payments.base import CheckoutRequest, ProviderError
from app.services.payments.prodamus import parse_form, sign

PAYMENT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
SECRET = "test_secret_key"


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


# --------------------------------------------------------------- the catalogue


def test_every_provider_satisfies_the_interface():
    from app.services.payments import PROVIDERS, describe_providers

    for slug, provider in PROVIDERS.items():
        assert provider.slug == slug
        assert provider.title and provider.hint, f"{slug} без названия или подсказки"
        assert provider.currencies, f"{slug} не объявил ни одной валюты"
        assert all(c.isupper() for c in provider.currencies), f"{slug}: валюты должны быть в верхнем регистре"

    described = describe_providers()
    assert {p["slug"] for p in described} == set(PROVIDERS)
    for entry in described:
        for field in entry["fields"] + entry["block_fields"]:
            # The catalogue is what the settings form renders from; a value
            # appearing here would mean a stored secret going to the browser.
            assert set(field) == {"key", "label", "hint", "secret"}


def test_every_provider_is_filed_under_a_real_region():
    """The settings form groups the catalogue by region and drops sections
    with nothing in them. A provider carrying a region that is not in
    REGIONS would therefore vanish from the UI entirely — installed,
    configurable through the API, and invisible to the only people who can
    configure it."""
    from app.services.payments import PROVIDERS, REGIONS, describe_providers

    known = {slug for slug, _title in REGIONS}
    assert len(known) == len(REGIONS), "в REGIONS повторяется slug"

    for slug, provider in PROVIDERS.items():
        assert provider.region in known, f"{slug}: неизвестный регион {provider.region!r}"

    # And the catalogue actually carries it — grouping reads this field, not
    # the Python attribute.
    for entry in describe_providers():
        assert entry["region"] in known

    # Every section that exists has something in it, or the heading would
    # be dead weight the form has to hide.
    used = {p.region for p in PROVIDERS.values()}
    assert used == known, f"пустые разделы: {known - used}"


# ------------------------------------------------------------------- Prodamus


def test_prodamus_parses_php_style_form_keys():
    parsed = parse_form(
        "order_id=abc&sum=990.00&payment_status=success"
        "&products%5B0%5D%5Bname%5D=%D0%93%D0%B0%D0%B9%D0%B4"
        "&products%5B0%5D%5Bprice%5D=990.00&products%5B0%5D%5Bquantity%5D=1"
    )

    assert parsed["order_id"] == "abc"
    # Numeric keys must become a JSON array, the way PHP's json_encode would
    # render them — an object keyed "0" signs to something else entirely.
    assert isinstance(parsed["products"], list)
    assert parsed["products"][0]["name"] == "Гайд"


def test_prodamus_signature_matches_an_independent_implementation():
    parsed = parse_form("order_id=abc&sum=990.00&payment_status=success")
    expected = hmac.new(
        SECRET.encode(),
        json.dumps(parsed, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(),
        hashlib.sha256,
    ).hexdigest()

    assert sign(parsed, SECRET) == expected


def test_prodamus_signature_ignores_the_signature_field_itself():
    parsed = parse_form("order_id=abc&sum=990.00")
    base = sign(parsed, SECRET)

    assert sign({**parsed, "signature": "что угодно"}, SECRET) == base
    assert sign({**parsed, "sign": "что угодно"}, SECRET) == base


def test_prodamus_leaves_unicode_and_slashes_unescaped():
    payload = {"url": "https://a.ru/b", "name": "Гайд «кофейня»"}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    assert "\\/" not in encoded and "\\u" not in encoded
    assert sign(payload, SECRET) == hmac.new(SECRET.encode(), encoded.encode(), hashlib.sha256).hexdigest()


async def test_prodamus_link_verifies_against_its_own_signature():
    """A full round trip: build the checkout URL, parse it back the way the
    callback arrives, and check the signature still holds."""
    checkout = await get_provider("prodamus").create_checkout(
        checkout_request({"shop_domain": "demo.payform.ru", "secret_key": SECRET})
    )

    round_tripped = parse_form(checkout.url.split("?", 1)[1])
    received = round_tripped.pop("signature")

    assert sign(round_tripped, SECRET) == received
    assert round_tripped["order_id"] == str(PAYMENT_ID)
    assert round_tripped["products"][0]["price"] == "990.00"


async def test_prodamus_accepts_a_valid_callback():
    body = f"order_id={PAYMENT_ID}&sum=990.00&payment_status=success&order_num=77"
    result = await get_provider("prodamus").verify_webhook(
        headers={"sign": sign(parse_form(body), SECRET)},
        raw_body=body.encode(),
        form={},
        credentials={"shop_domain": "demo.payform.ru", "secret_key": SECRET},
        amount_minor=99000,
        invoice_no=1234,
        payment_id=PAYMENT_ID,
        provider_payment_id=None,
    )

    assert result.status.value == "paid"
    # Prodamus treats anything but this exact body as a failed delivery.
    assert result.response_body == "success"


@pytest.mark.parametrize(
    ("body", "signature", "why"),
    [
        (f"order_id={PAYMENT_ID}&sum=990.00&payment_status=success", "deadbeef", "подпись не та"),
        (
            f"order_id={PAYMENT_ID}&sum=10.00&payment_status=success",
            None,  # correctly signed, but for a smaller amount
            "подпись верная, но сумма подменена",
        ),
    ],
)
async def test_prodamus_rejects_a_tampered_callback(body, signature, why):
    if signature is None:
        signature = sign(parse_form(body), SECRET)

    with pytest.raises(ProviderError):
        await get_provider("prodamus").verify_webhook(
            headers={"sign": signature},
            raw_body=body.encode(),
            form={},
            credentials={"shop_domain": "demo.payform.ru", "secret_key": SECRET},
            amount_minor=99000,
            invoice_no=1234,
            payment_id=PAYMENT_ID,
            provider_payment_id=None,
        )


# ------------------------------------------------------------------ Robokassa


async def test_robokassa_signs_the_checkout_link():
    checkout = await get_provider("robokassa").create_checkout(
        checkout_request({"merchant_login": "demo_shop", "password1": "pass1", "password2": "pass2"})
    )

    assert hashlib.md5(b"demo_shop:990.00:4242:pass1").hexdigest() in checkout.url
    assert "IsTest=1" in checkout.url


async def test_robokassa_accepts_a_valid_callback():
    form = {
        "OutSum": "990.00",
        "InvId": "4242",
        "SignatureValue": hashlib.md5(b"990.00:4242:pass2").hexdigest(),
    }

    result = await get_provider("robokassa").verify_webhook(
        headers={}, raw_body=b"", form=form,
        credentials={"merchant_login": "demo_shop", "password1": "pass1", "password2": "pass2"},
        amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID, provider_payment_id="4242",
    )

    assert result.status.value == "paid"
    assert result.response_body == "OK4242"  # Robokassa retries anything else


@pytest.mark.parametrize(
    ("form", "why"),
    [
        ({"OutSum": "990.00", "InvId": "4242", "SignatureValue": "deadbeef"}, "подпись не та"),
        (
            {"OutSum": "10.00", "InvId": "4242", "SignatureValue": hashlib.md5(b"10.00:4242:pass2").hexdigest()},
            "подпись верная, но сумма меньше заказанной",
        ),
    ],
)
async def test_robokassa_rejects_a_tampered_callback(form, why):
    with pytest.raises(ProviderError):
        await get_provider("robokassa").verify_webhook(
            headers={}, raw_body=b"", form=form,
            credentials={"merchant_login": "demo_shop", "password1": "pass1", "password2": "pass2"},
            amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID, provider_payment_id="4242",
        )


# --------------------------------------------------------------------- ЮKassa


def yookassa_api(status: str = "succeeded", value: str = "990.00"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={
                "id": "23d93cac-0000-5000-8000-126628f15141", "status": "pending",
                "confirmation": {"confirmation_url": "https://yoomoney.ru/checkout/abc"}})
        return httpx.Response(200, json={
            "id": "23d93cac-0000-5000-8000-126628f15141", "status": status,
            "paid": status == "succeeded", "amount": {"value": value, "currency": "RUB"}})

    return handler


YOOKASSA_CREDS = {"shop_id": "123456", "secret_key": "test_secret"}
YOOKASSA_HOOK = json.dumps(
    {"event": "payment.succeeded",
     "object": {"id": "23d93cac-0000-5000-8000-126628f15141", "metadata": {"order_id": str(PAYMENT_ID)}}}
).encode()


async def test_yookassa_sends_rubles_as_a_string_and_our_id_in_metadata(mock_http):
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return yookassa_api()(request)

    with mock_http(handler):
        checkout = await get_provider("yookassa").create_checkout(checkout_request(YOOKASSA_CREDS))

    body = json.loads(seen[-1].content)
    assert body["amount"] == {"value": "990.00", "currency": "RUB"}, "рубли строкой, не копейками"
    assert body["metadata"]["order_id"] == str(PAYMENT_ID)
    # Their idempotence key: a retried create can never charge twice.
    assert seen[-1].headers["Idempotence-Key"] == str(PAYMENT_ID)
    assert seen[-1].headers["Authorization"].startswith("Basic ")
    assert checkout.url == "https://yoomoney.ru/checkout/abc"


async def test_yookassa_believes_its_own_api_not_the_callback(mock_http):
    with mock_http(yookassa_api()):
        result = await get_provider("yookassa").verify_webhook(
            headers={}, raw_body=YOOKASSA_HOOK, form={}, credentials=YOOKASSA_CREDS,
            amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID,
            provider_payment_id="23d93cac-0000-5000-8000-126628f15141",
        )

    assert result.status.value == "paid"


async def test_yookassa_ignores_a_forged_success(mock_http):
    """The callback claims payment.succeeded; the API says it is still
    pending. Nothing may ship on the strength of an unsigned request body."""
    with mock_http(yookassa_api(status="pending")):
        result = await get_provider("yookassa").verify_webhook(
            headers={}, raw_body=YOOKASSA_HOOK, form={}, credentials=YOOKASSA_CREDS,
            amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID, provider_payment_id="x",
        )

    assert result.status.value == "pending"


async def test_yookassa_refuses_a_mismatched_amount(mock_http):
    with mock_http(yookassa_api(value="10.00")), pytest.raises(ProviderError):
        await get_provider("yookassa").verify_webhook(
            headers={}, raw_body=YOOKASSA_HOOK, form={}, credentials=YOOKASSA_CREDS,
            amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID, provider_payment_id="x",
        )


# ------------------------------------------------------------------ PayMaster


async def test_paymaster_sends_rubles_as_a_number_and_settles_only_after_a_read(mock_http):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"paymentId": "9fc2", "url": "https://paymaster.ru/pay/9fc2"})
        return httpx.Response(200, json={"id": "9fc2", "status": "Settled",
                                         "amount": {"value": 990.00, "currency": "RUB"}})

    creds = {"merchant_id": "0000-1111", "token": "tok"}
    with mock_http(handler):
        checkout = await get_provider("paymaster").create_checkout(checkout_request(creds))
        body = json.loads(seen[-1].content)
        assert body["amount"]["value"] == 990.0, "рубли числом"
        assert body["invoice"]["orderNo"] == str(PAYMENT_ID)
        assert body["testMode"] is True
        assert seen[-1].headers["Authorization"] == "Bearer tok"
        assert checkout.provider_payment_id == "9fc2"

        hook = json.dumps({"id": "9fc2", "status": "Settled", "invoice": {"orderNo": str(PAYMENT_ID)}}).encode()
        assert get_provider("paymaster").locate_payment(headers={}, raw_body=hook, form={}).payment_id == PAYMENT_ID

        result = await get_provider("paymaster").verify_webhook(
            headers={}, raw_body=hook, form={}, credentials=creds,
            amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID, provider_payment_id="9fc2",
        )

    assert result.status.value == "paid"
    assert seen[-1].method == "GET", "статус обязан подтверждаться обратным запросом"


# ------------------------------------------------------------------- LIFE PAY


async def test_lifepay_puts_the_bank_picker_in_the_button_and_matches_by_bill_number(mock_http):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"code": 0, "data": {
                "status": 15, "number": 18948962804043,
                "paymentUrl": "https://qr.nspk.ru/abc", "paymentUrlWeb": "https://web.qr.nspk.ru/abc"}})
        return httpx.Response(200, json={"code": 0, "data": {"status": 10, "amount": "990.00"}})

    creds = {"login": "79990000000", "apikey": "key", "method": "sbp"}
    with mock_http(handler):
        checkout = await get_provider("lifepay").create_checkout(checkout_request(creds))
        body = json.loads(seen[-1].content)
        # LIFE PAY takes its credentials in the body, not in headers.
        assert body["amount"] == "990.00" and body["apikey"] == "key" and body["login"] == "79990000000"
        assert checkout.url == "https://web.qr.nspk.ru/abc", "в кнопку идёт страница выбора банка"
        assert checkout.meta["sbp_url"] == "https://qr.nspk.ru/abc"
        assert checkout.provider_payment_id == "18948962804043"

        hook = json.dumps({"number": 18948962804043, "type": "payment", "status": "success"}).encode()
        # There is no order id anywhere in a LIFE PAY bill — their number is
        # the only handle back to our row.
        ref = get_provider("lifepay").locate_payment(headers={}, raw_body=hook, form={})
        assert ref.provider_payment_id == "18948962804043"

        result = await get_provider("lifepay").verify_webhook(
            headers={}, raw_body=hook, form={}, credentials=creds,
            amount_minor=99000, invoice_no=4242, payment_id=PAYMENT_ID,
            provider_payment_id="18948962804043",
        )

    assert result.status.value == "paid"
    assert seen[-1].method == "GET"


# ------------------------------------------------------------------- lava.top


LAVA_CREDS = {"api_key": "k", "buyer_email": "shop@example.com"}


async def test_lavatop_tags_the_invoice_so_the_webhook_can_be_matched(mock_http):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"id": "inv-1", "status": "new",
                                         "amountTotal": {"currency": "RUB", "amount": 990},
                                         "paymentUrl": "https://app.lava.top/payment/inv-1"})

    with mock_http(handler):
        checkout = await get_provider("lavatop").create_checkout(
            checkout_request(LAVA_CREDS, extra={"offer_id": "offer-uuid"})
        )

    body = json.loads(seen[-1].content)
    assert seen[-1].headers["X-Api-Key"] == "k"
    assert body["offerId"] == "offer-uuid"
    # Lava has no free order id field; utm_content is the one value that
    # survives the round trip into the webhook.
    assert body["clientUtm"]["utm_content"] == str(PAYMENT_ID)
    assert checkout.provider_payment_id == "inv-1"


async def test_lavatop_refuses_when_the_offer_price_differs_from_the_block(mock_http):
    """The offer decides the price, so a mismatch has to surface here rather
    than as a buyer charged an amount the bot never showed them."""
    def handler(request):
        return httpx.Response(201, json={"id": "inv-1", "status": "new",
                                         "amountTotal": {"currency": "RUB", "amount": 490},
                                         "paymentUrl": "https://app.lava.top/payment/inv-1"})

    with mock_http(handler), pytest.raises(ProviderError, match="490"):
        await get_provider("lavatop").create_checkout(
            checkout_request(LAVA_CREDS, extra={"offer_id": "offer-uuid"})
        )


async def test_lavatop_needs_an_offer_id():
    with pytest.raises(ProviderError, match="offerId"):
        await get_provider("lavatop").create_checkout(checkout_request(LAVA_CREDS))


# ----------------------------------------------------------- pay-by-link, test


async def test_link_provider_uses_the_pasted_url():
    checkout = await get_provider("link").create_checkout(
        checkout_request({}, extra={"link_url": "https://boosty.to/shop/x"})
    )

    assert checkout.url == "https://boosty.to/shop/x"


@pytest.mark.parametrize("bad", ["", "не ссылка", "boosty.to/shop"])
async def test_link_provider_refuses_something_that_is_not_a_link(bad):
    """Telegram rejects a button whose url isn't absolute, and that failure
    would otherwise swallow the whole message."""
    with pytest.raises(ProviderError):
        await get_provider("link").create_checkout(checkout_request({}, extra={"link_url": bad}))


async def test_test_provider_refuses_live_mode():
    request = CheckoutRequest(
        payment_id=PAYMENT_ID, invoice_no=1, amount_minor=100, currency="KZT",
        description="x", return_url="https://example.com", is_test=False, credentials={},
    )

    with pytest.raises(ProviderError):
        await get_provider("test").create_checkout(request)


# --------------------------------------------------------------------- Stars


def test_stars_price_must_be_a_whole_number_of_stars():
    from app.services.payments.telegram_stars import stars_from_minor

    assert stars_from_minor(25000) == 250

    # 250.50 stars cannot be charged, and rounding it away would mis-price
    # the product rather than fail visibly.
    with pytest.raises(ProviderError):
        stars_from_minor(25050)
    with pytest.raises(ProviderError):
        stars_from_minor(0)


def test_stars_refuses_a_payment_for_the_wrong_amount():
    from app.services.payments.telegram_stars import settled

    assert settled(charge_id="chg", total_amount=250, amount_minor=25000).status.value == "paid"

    with pytest.raises(ProviderError):
        settled(charge_id="chg", total_amount=5, amount_minor=25000)


# ----------------------------------------------------------------- Crypto Bot


CRYPTO_TOKEN = "12345:AAtestcryptotoken"
CRYPTO_CREDS = {"token": CRYPTO_TOKEN}


def crypto_signature(body: bytes) -> str:
    """Their scheme: HMAC-SHA256 of the update body, keyed on the SHA256 of
    the API token. Recomputed independently of the adapter."""
    key = hashlib.sha256(CRYPTO_TOKEN.encode()).digest()
    return hmac.new(key, body, hashlib.sha256).hexdigest()


async def test_cryptobot_creates_an_invoice_tagged_with_our_payment_id(mock_http):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "result": {
            "invoice_id": 778899, "status": "active", "asset": "USDT", "amount": "990.00",
            "bot_invoice_url": "https://t.me/CryptoBot?start=IV123",
            "web_app_invoice_url": "https://app.crypt.bot/invoice/IV123"}})

    with mock_http(handler):
        checkout = await get_provider("cryptobot").create_checkout(
            checkout_request(CRYPTO_CREDS, currency="USDT")
        )

    # The API takes query parameters, not a JSON body.
    query = dict(seen[-1].url.params)
    assert query["asset"] == "USDT"
    assert query["amount"] == "990.00"
    assert query["payload"] == str(PAYMENT_ID), "payload is the only field that returns in the webhook"
    assert seen[-1].headers["Crypto-Pay-API-Token"] == CRYPTO_TOKEN
    # The paywall lives on the web, so the browser link is preferred.
    assert checkout.url == "https://app.crypt.bot/invoice/IV123"
    assert checkout.provider_payment_id == "778899"


async def test_cryptobot_reports_an_api_error_rather_than_a_bare_failure(mock_http):
    with mock_http(lambda r: httpx.Response(200, json={"ok": False, "error": {"code": 401, "name": "UNAUTHORIZED"}})):
        with pytest.raises(ProviderError, match="UNAUTHORIZED"):
            await get_provider("cryptobot").create_checkout(checkout_request(CRYPTO_CREDS, currency="USDT"))


async def test_cryptobot_rejects_an_unsigned_callback(mock_http):
    body = json.dumps({"update_type": "invoice_paid", "payload": {"invoice_id": 778899, "status": "paid"}}).encode()

    with mock_http(lambda r: httpx.Response(200, json={"ok": True, "result": {"items": []}})):
        with pytest.raises(ProviderError, match="одпись"):
            await get_provider("cryptobot").verify_webhook(
                headers={"crypto-pay-api-signature": "deadbeef"}, raw_body=body, form={},
                credentials=CRYPTO_CREDS, amount_minor=99000, invoice_no=1,
                payment_id=PAYMENT_ID, provider_payment_id="778899",
            )


async def test_cryptobot_believes_the_api_not_the_signed_callback(mock_http):
    """A correctly signed callback still proves only that the message is
    theirs — the invoice is read back before anything ships."""
    body = json.dumps({
        "update_type": "invoice_paid",
        "payload": {"invoice_id": 778899, "status": "paid", "payload": str(PAYMENT_ID)},
    }).encode()

    def unpaid(request):
        return httpx.Response(200, json={"ok": True, "result": {
            "items": [{"invoice_id": 778899, "status": "active", "amount": "990.00"}]}})

    with mock_http(unpaid):
        result = await get_provider("cryptobot").verify_webhook(
            headers={"crypto-pay-api-signature": crypto_signature(body)}, raw_body=body, form={},
            credentials=CRYPTO_CREDS, amount_minor=99000, invoice_no=1,
            payment_id=PAYMENT_ID, provider_payment_id="778899",
        )

    assert result.status.value == "pending"

    def paid(request):
        return httpx.Response(200, json={"ok": True, "result": {
            "items": [{"invoice_id": 778899, "status": "paid", "amount": "990.00"}]}})

    with mock_http(paid):
        result = await get_provider("cryptobot").verify_webhook(
            headers={"crypto-pay-api-signature": crypto_signature(body)}, raw_body=body, form={},
            credentials=CRYPTO_CREDS, amount_minor=99000, invoice_no=1,
            payment_id=PAYMENT_ID, provider_payment_id="778899",
        )

    assert result.status.value == "paid"


async def test_cryptobot_refuses_an_invoice_paid_for_less(mock_http):
    body = json.dumps({"update_type": "invoice_paid", "payload": {"invoice_id": 778899}}).encode()

    def short(request):
        return httpx.Response(200, json={"ok": True, "result": {
            "items": [{"invoice_id": 778899, "status": "paid", "amount": "1.00"}]}})

    with mock_http(short), pytest.raises(ProviderError, match="сумма"):
        await get_provider("cryptobot").verify_webhook(
            headers={"crypto-pay-api-signature": crypto_signature(body)}, raw_body=body, form={},
            credentials=CRYPTO_CREDS, amount_minor=99000, invoice_no=1,
            payment_id=PAYMENT_ID, provider_payment_id="778899",
        )


def test_cryptobot_finds_the_payment_by_our_own_payload():
    body = json.dumps({
        "update_type": "invoice_paid",
        "payload": {"invoice_id": 778899, "payload": str(PAYMENT_ID)},
    }).encode()

    ref = get_provider("cryptobot").locate_payment(headers={}, raw_body=body, form={})

    assert ref.payment_id == PAYMENT_ID
