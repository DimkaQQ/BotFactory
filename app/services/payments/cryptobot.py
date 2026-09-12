"""Crypto Bot (@CryptoBot) — Crypto Pay API.

The one crypto route that needs no company and no KYC: an app is created
inside @CryptoBot, which hands over an API token, and the buyer pays from
their Telegram wallet in USDT, TON, BTC and a few others.

Two details differ from every other adapter here:

* the API is called with **query parameters**, not a JSON body, and answers
  with an `{"ok": bool, "result": …}` envelope;
* an invoice is denominated in a crypto asset rather than a fiat currency,
  so `currency` on the payment holds "USDT" or "TON".

Its webhooks *are* signed — HMAC-SHA256 with a key that is itself the SHA256
of the API token — but the signature is treated as a first gate rather than
the answer: the invoice is read back through `getInvoices` before anything
ships, the same as for the providers that sign nothing.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import httpx

from app.models.payment import PaymentStatus
from app.services.payments.base import (
    Checkout,
    CheckoutRequest,
    CredentialField,
    PaymentRef,
    ProviderDefaults,
    ProviderError,
    WebhookResult,
    same_currency,
)

_MAINNET = "https://pay.crypt.bot/api"
_TESTNET = "https://testnet-pay.crypt.bot/api"

# The pay link has been renamed across API versions; take whichever is
# present, preferring the one that opens in a browser since the publication
# paywall lives on the web rather than inside Telegram.
_URL_FIELDS = ("web_app_invoice_url", "bot_invoice_url", "mini_app_invoice_url", "pay_url")


class CryptoBotProvider(ProviderDefaults):
    slug = "cryptobot"
    title = "Crypto Bot (USDT, TON)"
    hint = (
        "Открой @CryptoBot в Telegram → Crypto Pay → Create App, скопируй токен приложения сюда. "
        "Юрлицо и KYC не нужны. Покупатель платит прямо из своего кошелька в Telegram. "
        "Адрес для уведомлений задаётся там же (Crypto Pay → My Apps → Webhooks) — мы всё равно "
        "перепроверяем счёт запросом в их API, так что подпись не единственная защита."
    )
    # Assets the Crypto Pay API issues invoices in.
    currencies = ("USDT", "TON", "BTC", "ETH", "USDC", "BUSD")
    supports_status_check = True
    credential_fields = (CredentialField("token", "Токен приложения", "из @CryptoBot → Crypto Pay → Create App"),)

    @staticmethod
    def _token(credentials: dict[str, str]) -> str:
        token = (credentials.get("token") or "").strip()
        if not token:
            raise ProviderError("Crypto Bot: не заполнен токен приложения")
        return token

    @staticmethod
    def _base(is_test: bool) -> str:
        return _TESTNET if is_test else _MAINNET

    @classmethod
    async def _call(cls, method: str, credentials: dict[str, str], is_test: bool, **params) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{cls._base(is_test)}/{method}",
                params={k: v for k, v in params.items() if v not in (None, "")},
                headers={"Crypto-Pay-API-Token": cls._token(credentials)},
            )
        try:
            payload = response.json()
        except ValueError:
            raise ProviderError(f"Crypto Bot: {response.text[:200]}") from None

        if not payload.get("ok"):
            raise ProviderError(f"Crypto Bot: {json.dumps(payload.get('error') or payload, ensure_ascii=False)[:200]}")
        return payload.get("result") or {}

    @staticmethod
    def _amount(amount_minor: int) -> str:
        whole, hundredths = divmod(amount_minor, 100)
        return f"{whole}.{hundredths:02d}"

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        invoice = await self._call(
            "createInvoice",
            request.credentials,
            request.is_test,
            asset=request.currency.upper(),
            amount=self._amount(request.amount_minor),
            description=request.description[:1024] or "Оплата",
            # Comes back verbatim in the webhook — how a payment is matched.
            payload=str(request.payment_id),
            paid_btn_name="openBot" if request.return_url.startswith("https://t.me/") else "openChannel",
            paid_btn_url=request.return_url,
            expires_in=3600,
        )

        url = next((invoice[field] for field in _URL_FIELDS if invoice.get(field)), None)
        if not url:
            raise ProviderError("Crypto Bot: ответ без ссылки на оплату")

        invoice_id = invoice.get("invoice_id")
        return Checkout(
            url=url,
            provider_payment_id=str(invoice_id) if invoice_id is not None else None,
            meta={
                "asset": invoice.get("asset"),
                "crypto_amount": invoice.get("amount"),
                # Mainnet and testnet are separate ledgers that know
                # nothing of each other; asking the wrong one first cost a
                # failing round trip on every single callback.
                "is_test": request.is_test,
            },
        )

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        try:
            update = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            return PaymentRef()

        invoice = update.get("payload") if isinstance(update.get("payload"), dict) else update
        try:
            return PaymentRef(payment_id=uuid.UUID(str(invoice.get("payload") or "")))
        except (ValueError, AttributeError):
            pass
        invoice_id = invoice.get("invoice_id")
        return PaymentRef(provider_payment_id=str(invoice_id)) if invoice_id is not None else PaymentRef()

    @staticmethod
    def _signature_ok(token: str, raw_body: bytes, received: str) -> bool:
        """HMAC-SHA256 of the update body, keyed on SHA256 of the API token.

        Signed over the bytes as they were sent: re-serialising the parsed
        JSON would have to reproduce their exact key order and spacing, and
        any difference reads as forgery.
        """
        key = hashlib.sha256(token.encode()).digest()
        expected = hmac.new(key, raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, (received or "").strip())

    async def verify_webhook(
        self,
        *,
        headers: dict[str, str],
        raw_body: bytes,
        form: dict[str, str],
        credentials: dict[str, str],
        amount_minor: int,
        invoice_no: int,
        payment_id: uuid.UUID,
        provider_payment_id: str | None,
        meta: dict | None = None,
        currency: str = "",
    ) -> WebhookResult:
        token = self._token(credentials)
        if not self._signature_ok(token, raw_body, headers.get("crypto-pay-api-signature", "")):
            raise ProviderError("Crypto Bot: подпись уведомления не совпала")

        try:
            update = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            update = {}
        if update.get("update_type") not in (None, "invoice_paid"):
            return WebhookResult(status=PaymentStatus.pending, provider_payment_id=provider_payment_id)

        invoice = update.get("payload") if isinstance(update.get("payload"), dict) else {}
        remote_id = provider_payment_id or invoice.get("invoice_id")
        if remote_id is None:
            raise ProviderError("Crypto Bot: в уведомлении нет invoice_id")

        # The signature says the message is theirs; the API says what it is
        # worth. Only the second one releases the goods.
        return await self._read(
            credentials, str(remote_id), amount_minor, is_test=bool((meta or {}).get("is_test")), currency=currency
        )

    async def check_status(
        self,
        *,
        credentials: dict[str, str],
        amount_minor: int,
        invoice_no: int,
        payment_id: uuid.UUID,
        provider_payment_id: str | None,
        meta: dict,
        currency: str = "",
    ) -> WebhookResult:
        if not provider_payment_id:
            raise ProviderError("Crypto Bot: счёт ещё не создан")
        return await self._read(
            credentials, provider_payment_id, amount_minor, is_test=bool(meta.get("is_test")), currency=currency
        )

    async def _read(
        self,
        credentials: dict[str, str],
        invoice_id: str,
        amount_minor: int,
        *,
        is_test: bool,
        currency: str = "",
    ) -> WebhookResult:
        result = await self._call("getInvoices", credentials, is_test, invoice_ids=invoice_id, count=1)
        items = result.get("items") if isinstance(result, dict) else result
        if not items:
            # Older payments were stored before the ledger was recorded, so
            # fall back to the other one rather than losing them.
            result = await self._call(
                "getInvoices", credentials, not is_test, invoice_ids=invoice_id, count=1
            )
            items = result.get("items") if isinstance(result, dict) else result
        if not items:
            raise ProviderError(f"Crypto Bot: счёт {invoice_id} не найден")

        invoice = items[0]
        status = str(invoice.get("status") or "").lower()

        if status == "paid":
            paid = invoice.get("amount")
            if paid is not None and abs(float(paid) - amount_minor / 100) > 0.0000001:
                raise ProviderError(f"Crypto Bot: сумма не совпадает (оплачено {paid})")
            # Crypto Bot calls it an asset, not a currency, but it is the same
            # question: 990 USDT and 990 TON are very different sales.
            same_currency(self.title, invoice.get("asset"), currency)
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=str(invoice_id))
        if status == "expired":
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=str(invoice_id))
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(invoice_id))
