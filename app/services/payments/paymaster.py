"""PayMaster — REST API v2 (invoice → payment link).

The public v2 docs describe no webhook signature, so the callback is
treated as a hint only and the truth comes from `GET /api/v2/payments/{id}`.
Goods ship on `Settled`.
"""

from __future__ import annotations

import json
import uuid

import httpx

from app.models.payment import PaymentStatus
from app.services.payments.base import (
    Checkout,
    CheckoutRequest,
    CredentialField,
    PaymentRef,
    PayMethod,
    PayObject,
    ProviderDefaults,
    ProviderError,
    Receipt,
    RecurringMode,
    RecurringSetup,
    Vat,
    WebhookResult,
    receipt_from_credentials,
    same_currency,
)

_BASE = "https://paymaster.ru/api/v2"
_SETTLED = {"settled"}
_REFUNDED = {"refunded", "partiallyrefunded", "partially_refunded"}
_FAILED = {"cancelled", "rejected"}


# Значения справочника PayMaster API v2 — CamelCase.
PM_VAT = {
    Vat.NONE: "None", Vat.VAT0: "Vat0", Vat.VAT5: "Vat5", Vat.VAT7: "Vat7", Vat.VAT10: "Vat10",
    Vat.VAT22: "Vat22", Vat.VAT105: "Vat105", Vat.VAT107: "Vat107", Vat.VAT110: "Vat110", Vat.VAT122: "Vat122",
}  # fmt: skip
PM_METHOD = {
    PayMethod.FULL_PREPAYMENT: "FullPrepayment", PayMethod.PREPAYMENT: "Prepayment",
    PayMethod.ADVANCE: "Advance", PayMethod.FULL_PAYMENT: "FullPayment",
}  # fmt: skip
PM_OBJECT = {PayObject.SERVICE: "Service", PayObject.COMMODITY: "Commodity", PayObject.PAYMENT: "Payment"}


def receipt_paymaster(r: Receipt) -> dict:
    client = {k: (v.lstrip("+") if k == "phone" else v) for k, v in (("email", r.email), ("phone", r.phone)) if v}
    return {
        "client": client,
        "items": [
            {
                "name": i.name,
                "quantity": float(i.qty),
                "price": float(i.price),
                "vatType": PM_VAT[i.vat],
                "paymentSubject": PM_OBJECT[i.obj],
                "paymentMethod": PM_METHOD[i.method],
            }
            for i in r.items
        ],
    }


class PayMasterProvider(ProviderDefaults):
    slug = "paymaster"
    title = "PayMaster"
    hint = (
        "Токен — в кабинете мерчанта, «Настройки → Токены доступа». merchantId (UUID сайта) там же, в списке "
        "сайтов. Адрес уведомления мы передаём в самом счёте, отдельно настраивать не нужно."
    )
    currencies = ("RUB",)
    region = "ru"
    supports_status_check = True
    #: Адрес уведомлений уходит в каждом платеже сам — вписывать его в кабинете не нужно.
    sends_own_callback_url = True
    # Хостируемая токенизация: объект tokenization в счёте, id токена
    # приходит и в ответе, и в колбэке, списание — POST /payments с
    # paymentData.token.id. Деньги только на Settled: Confirmation и
    # Pending — это ещё не оплата.
    recurring = RecurringMode.token
    credential_fields = (
        CredentialField("merchant_id", "merchantId", "UUID сайта в PayMaster", secret=False),
        CredentialField("token", "Токен доступа", "из раздела «Токены доступа»"),
        # Чек 54-ФЗ: передаётся, только если указана почта. Сумма чека всегда равна сумме платежа.
        CredentialField(
            "fiscalization_enabled", "Передавать чек (54-ФЗ)", "1 — да, 0 или пусто — нет. Включай, только если у кассы подключена онлайн-касса",
            secret=False, required=False,
        ),
        CredentialField("fiscal_email", "Почта для чеков (если нужна фискализация)", "email для чека 54-ФЗ", secret=False, required=False),
        CredentialField(
            "tax_system", "Система налогообложения", "osn, usn_income (по умолчанию), usn_income_outcome, esn, patent", secret=False, required=False),
        CredentialField(
            "default_vat", "Ставка НДС в чеке", "none (по умолчанию), vat0, vat5, vat7, vat10, vat22", secret=False, required=False),
    )

    @staticmethod
    def _headers(credentials: dict[str, str]) -> dict[str, str]:
        token = (credentials.get("token") or "").strip()
        if not token:
            raise ProviderError("PayMaster: не заполнен токен доступа")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        headers = self._headers(request.credentials)
        merchant_id = (request.credentials.get("merchant_id") or "").strip()
        if not merchant_id:
            raise ProviderError("PayMaster: не заполнен merchantId")

        from app.config import get_settings

        base = get_settings().public_base_url.rstrip("/")
        body = {
            "merchantId": merchant_id,
            "invoice": {
                "description": request.description[:255] or "Оплата",
                # Our payment id rides back in the callback as orderNo.
                "orderNo": str(request.payment_id),
            },
            "amount": {"value": round(request.amount_minor / 100, 2), "currency": request.currency.upper()},
            "protocol": {
                "returnUrl": request.return_url,
                "callbackUrl": f"{base}/webhook/pay/paymaster",
            },
            "testMode": request.is_test,
        }
        receipt = receipt_from_credentials(
            request.credentials, request.description, request.amount_minor,
            buyer_email=request.buyer_email, buyer_phone=request.buyer_phone,
        )
        if receipt:
            body["receipt"] = receipt_paymaster(receipt)
        if request.extra.get("subscription"):
            # PayMaster hosts the card form, so no PAN ever reaches us; what
            # comes back is a token id. `purpose` is the consent text the
            # payer is shown, so it has to name the actual arrangement.
            body["tokenization"] = {
                "type": "recurring",
                "purpose": (request.description or "Подписка")[:255],
                "callbackUrl": f"{base}/webhook/pay/paymaster",
            }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{_BASE}/invoices", json=body, headers={**headers, "Idempotency-Key": str(request.payment_id)}
            )
        if response.status_code >= 400:
            raise ProviderError(f"PayMaster: {_error(response)}")

        payload = response.json()
        url = payload.get("url")
        if not url:
            raise ProviderError("PayMaster: ответ без ссылки на оплату")
        return Checkout(url=url, provider_payment_id=payload.get("paymentId"))

    @staticmethod
    def _token_id(payment: dict) -> str:
        """The saved-card handle, wherever this response happens to put it."""
        # По документации PayMaster в деталях платежа токен лежит в `paymentToken{id}`.
        saved = payment.get("paymentToken")
        if isinstance(saved, dict) and saved.get("id"):
            return str(saved["id"])
        for holder in (payment.get("paymentData") or {}, payment):
            token = holder.get("token")
            if isinstance(token, dict) and token.get("id"):
                return str(token["id"])
            if isinstance(token, str) and token:
                return token
        tokenization = payment.get("tokenization") or {}
        return str(tokenization.get("id") or "") if tokenization.get("id") else ""

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        try:
            event = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            return PaymentRef()
        order_no = (event.get("invoice") or {}).get("orderNo", "")
        try:
            return PaymentRef(payment_id=uuid.UUID(str(order_no)))
        except (ValueError, AttributeError):
            return PaymentRef(provider_payment_id=str(event.get("id")) if event.get("id") else None)

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
        try:
            event = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            event = {}
        remote_id = provider_payment_id or event.get("id")
        if not remote_id:
            raise ProviderError("PayMaster: не удалось определить платёж")
        return await self._read(credentials, str(remote_id), amount_minor, currency)

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
            raise ProviderError("PayMaster: платёж ещё не создан")
        return await self._read(credentials, provider_payment_id, amount_minor, currency)

    async def _read(
        self, credentials: dict[str, str], remote_id: str, amount_minor: int, currency: str = ""
    ) -> WebhookResult:
        """What PayMaster itself says about the payment — the only thing
        believed here, whether prompted by a callback or by the buyer."""
        api_headers = self._headers(credentials)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{_BASE}/payments/{remote_id}", headers=api_headers)
        if response.status_code >= 400:
            raise ProviderError(f"PayMaster: {_error(response)}")

        payment = response.json()
        status = str(payment.get("status", "")).lower()
        if status in _SETTLED:
            value = (payment.get("amount") or {}).get("value")
            if value is not None and abs(float(value) - amount_minor / 100) > 0.009:
                raise ProviderError(f"PayMaster: сумма не совпадает (у провайдера {value})")
            same_currency(self.title, (payment.get("amount") or {}).get("currency"), currency)
            token = self._token_id(payment)
            return WebhookResult(
                status=PaymentStatus.paid,
                provider_payment_id=str(remote_id),
                meta={"paymaster_token_id": token} if token else {},
            )
        if status in _REFUNDED:
            return WebhookResult(status=PaymentStatus.refunded, provider_payment_id=str(remote_id))
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=str(remote_id))
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(remote_id))


    def recurring_setup(self, settled: dict) -> RecurringSetup | None:
        token = (settled or {}).get("paymaster_token_id")
        return RecurringSetup(token=str(token)) if token else None

    async def charge_recurring(
        self,
        *,
        credentials: dict[str, str],
        setup: RecurringSetup,
        amount_minor: int,
        currency: str,
        description: str,
        payment_id: uuid.UUID,
        is_test: bool = False,
        invoice_no: int | None = None,
    ) -> WebhookResult:
        """Charge the saved token. Only `Settled` counts as money.

        The response comes back immediately but is not final: `Confirmation`
        means PayMaster still wants something from the payer, and `Pending`
        means it is still deciding. Both are reported as pending, and the
        ordinary callback settles the payment when it resolves — the same
        route a hand-made payment takes.
        """
        from app.config import get_settings

        headers = self._headers(credentials)
        merchant_id = (credentials.get("merchant_id") or "").strip()
        if not merchant_id:
            raise ProviderError("PayMaster: не заполнен merchantId")
        if not setup.token:
            raise ProviderError("PayMaster: нет сохранённого токена карты")

        base = get_settings().public_base_url.rstrip("/")
        body = {
            "merchantId": merchant_id,
            "invoice": {
                "description": (description or "Продление подписки")[:255],
                "orderNo": str(payment_id),
            },
            "amount": {"value": round(amount_minor / 100, 2), "currency": currency.upper()},
            "paymentData": {"token": {"id": setup.token}},
            "protocol": {"callbackUrl": f"{base}/webhook/pay/paymaster"},
            "testMode": bool(is_test),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{_BASE}/payments", json=body, headers={**headers, "Idempotency-Key": str(payment_id)}
            )
        if response.status_code >= 400:
            raise ProviderError(f"PayMaster: {_error(response)}")

        payload = response.json()
        remote_id = payload.get("paymentId") or payload.get("id")
        status = str(payload.get("status", "")).lower()
        if status in _SETTLED:
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=str(remote_id or ""))
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=str(remote_id or ""))
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(remote_id or ""))


def _error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return payload.get("message") or payload.get("error") or response.text[:200]
    except ValueError:
        return response.text[:200]
