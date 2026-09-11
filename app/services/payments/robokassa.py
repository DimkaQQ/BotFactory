"""Robokassa — a signed redirect link, no API call needed to start.

Checkout is a plain URL whose SignatureValue is md5 of
"MerchantLogin:OutSum:InvId:Password1"; the ResultURL callback carries
"OutSum:InvId:Password2" and expects the literal body "OK{InvId}" back,
retrying until it gets one.
"""

from __future__ import annotations

import hashlib
import uuid
from urllib.parse import urlencode

from app.models.payment import PaymentStatus
from app.services.payments.base import (
    Checkout,
    CheckoutRequest,
    CredentialField,
    PaymentRef,
    ProviderDefaults,
    ProviderError,
    WebhookResult,
    minor_to_major,
)

_CHECKOUT_URL = "https://auth.robokassa.ru/Merchant/Index.aspx"


class RobokassaProvider(ProviderDefaults):
    slug = "robokassa"
    title = "Robokassa"
    hint = (
        "Логин магазина и оба пароля — в личном кабинете Robokassa, раздел «Технические настройки». "
        "Там же укажи Result URL, который мы покажем ниже, и метод отправки POST. Счёт выставляется в валюте твоего магазина Robokassa — для тенге удобнее Freedom Pay, ioka или CloudPayments."
    )
    currencies = ("RUB",)
    credential_fields = (
        CredentialField("merchant_login", "Идентификатор магазина", "MerchantLogin из кабинета", secret=False),
        CredentialField("password1", "Пароль #1", "Используется для подписи ссылки на оплату"),
        CredentialField("password2", "Пароль #2", "Используется для проверки уведомления об оплате"),
    )

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        login = (request.credentials.get("merchant_login") or "").strip()
        password1 = (request.credentials.get("password1") or "").strip()
        if not login or not password1:
            raise ProviderError("Robokassa: не заполнены идентификатор магазина или пароль #1")

        out_sum = minor_to_major(request.amount_minor)
        signature = hashlib.md5(f"{login}:{out_sum}:{request.invoice_no}:{password1}".encode()).hexdigest()

        params = {
            "MerchantLogin": login,
            "OutSum": out_sum,
            "InvId": str(request.invoice_no),
            "Description": request.description[:100] or "Оплата",
            "SignatureValue": signature,
            "Culture": "ru",
            "Encoding": "utf-8",
            "SuccessURL2": request.return_url,
        }
        # `OutSumCurrency` is deliberately not sent. With it, Robokassa
        # converts and then reports ResultURL's OutSum in the shop's *base*
        # currency — which no longer matches the block price, so the amount
        # check below would reject every callback forever while Robokassa
        # retried, and the buyer would never be delivered to. Without it,
        # both sides speak the shop's base currency and the check holds.
        #
        # That is why `currencies` is roubles only: a shop whose Robokassa
        # account is in tenge is better served by Freedom Pay, ioka or
        # CloudPayments, all of which say outright which currency they are
        # charging. Guessing here is how a 990 ₸ product gets sold for 990 ₽.
        if request.is_test:
            params["IsTest"] = "1"

        return Checkout(url=f"{_CHECKOUT_URL}?{urlencode(params)}", provider_payment_id=str(request.invoice_no))

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        raw = (form.get("InvId") or form.get("inv_id") or "").strip()
        try:
            return PaymentRef(invoice_no=int(raw))
        except ValueError:
            return PaymentRef()

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
        password2 = (credentials.get("password2") or "").strip()
        if not password2:
            raise ProviderError("Robokassa: не заполнен пароль #2")

        out_sum = (form.get("OutSum") or "").strip()
        received = (form.get("SignatureValue") or "").strip().lower()
        expected = hashlib.md5(f"{out_sum}:{invoice_no}:{password2}".encode()).hexdigest()
        if not received or received != expected:
            raise ProviderError("Robokassa: подпись уведомления не совпала")

        # The signature proves the callback is Robokassa's; this proves it is
        # about the amount we actually asked for, not a smaller one.
        # Compared as a number, not as text: Robokassa may send "990.0" or
        # "990.000" for the same amount, and a string mismatch would reject a
        # legitimate callback forever — it retries until acknowledged.
        try:
            mismatch = abs(float(out_sum.replace(",", ".")) - amount_minor / 100) > 0.009
        except ValueError:
            mismatch = True
        if mismatch:
            raise ProviderError(f"Robokassa: сумма не совпадает (пришло {out_sum})")

        return WebhookResult(
            status=PaymentStatus.paid,
            provider_payment_id=str(invoice_no),
            response_body=f"OK{invoice_no}",
        )
