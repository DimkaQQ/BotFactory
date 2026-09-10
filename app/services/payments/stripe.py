"""Stripe — a Checkout Session created over the REST API.

No SDK on purpose: one form-encoded POST and one HMAC check is the whole
integration, and httpx is already a dependency. The webhook signature is
Stripe's standard scheme — `Stripe-Signature: t=<ts>,v1=<hex>` over
"<ts>.<raw body>" with the endpoint secret.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
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
)

_API_URL = "https://api.stripe.com/v1/checkout/sessions"
# Stripe rejects a signature older than its tolerance to stop replays; five
# minutes is their documented default.
_SIGNATURE_TOLERANCE_S = 300
# Currencies Stripe charges without decimals — sending 990_00 for JPY would
# bill a hundred times too much.
_ZERO_DECIMAL = {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}


class StripeProvider(ProviderDefaults):
    slug = "stripe"
    title = "Stripe"
    hint = "Secret key (sk_live_… или sk_test_…) — в Stripe Dashboard → Developers → API keys. Webhook secret (whsec_…) появится, когда добавишь наш URL в Developers → Webhooks на событие checkout.session.completed."
    currencies = ("USD", "EUR", "GBP", "KZT", "PLN", "TRY", "AED")
    credential_fields = (
        CredentialField("secret_key", "Secret key", "sk_live_… или sk_test_…"),
        CredentialField("webhook_secret", "Webhook signing secret", "whsec_… из настроек вебхука"),
    )

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        secret_key = (request.credentials.get("secret_key") or "").strip()
        if not secret_key:
            raise ProviderError("Stripe: не заполнен secret key")

        currency = request.currency.lower()
        unit_amount = request.amount_minor // 100 if currency.upper() in _ZERO_DECIMAL else request.amount_minor

        data = {
            "mode": "payment",
            "success_url": request.return_url,
            "cancel_url": request.return_url,
            "client_reference_id": str(request.payment_id),
            "metadata[payment_id]": str(request.payment_id),
            "metadata[invoice_no]": str(request.invoice_no),
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": currency,
            "line_items[0][price_data][unit_amount]": str(unit_amount),
            "line_items[0][price_data][product_data][name]": request.description[:250] or "Оплата",
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(_API_URL, data=data, auth=(secret_key, ""))
        if response.status_code >= 400:
            detail = response.json().get("error", {}).get("message", response.text[:200])
            raise ProviderError(f"Stripe: {detail}")

        payload = response.json()
        url = payload.get("url")
        if not url:
            raise ProviderError("Stripe: ответ без ссылки на оплату")
        return Checkout(url=url, provider_payment_id=payload.get("id"))

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        # Parsed unverified, purely to find the row — the signature is checked
        # in verify_webhook, before anything is believed.
        try:
            event = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            return PaymentRef()
        obj = (event.get("data") or {}).get("object") or {}
        raw_id = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("payment_id") or ""
        try:
            return PaymentRef(payment_id=uuid.UUID(raw_id))
        except (ValueError, AttributeError):
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
    ) -> WebhookResult:
        secret = (credentials.get("webhook_secret") or "").strip()
        if not secret:
            raise ProviderError("Stripe: не заполнен webhook secret")

        header = headers.get("stripe-signature") or ""
        timestamp = None
        signatures = []
        for item in header.split(","):
            key, _, value = item.strip().partition("=")
            if key == "t":
                timestamp = value
            elif key == "v1":
                # During a secret rotation Stripe signs one delivery with
                # every active secret, so the header carries several `v1=`
                # entries. Collapsing them into a dict kept only the last and
                # rejected a legitimate callback.
                signatures.append(value)

        if not timestamp or not signatures:
            raise ProviderError("Stripe: заголовок подписи отсутствует или повреждён")
        if abs(time.time() - int(timestamp)) > _SIGNATURE_TOLERANCE_S:
            raise ProviderError("Stripe: подпись просрочена")

        expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
            raise ProviderError("Stripe: подпись не совпала")

        event = json.loads(raw_body or b"{}")
        obj = (event.get("data") or {}).get("object") or {}
        event_type = event.get("type", "")

        if event_type == "checkout.session.completed" and obj.get("payment_status") == "paid":
            # Every other adapter here cross-checks the amount before letting
            # the goods go; Stripe gets the same treatment rather than being
            # trusted purely because the signature held.
            charged = obj.get("amount_total")
            currency = (obj.get("currency") or "").upper()
            expected = amount_minor // 100 if currency in _ZERO_DECIMAL else amount_minor
            if charged is not None and int(charged) != expected:
                raise ProviderError(f"Stripe: сумма не совпадает (оплачено {charged}, ожидалось {expected})")
            status = PaymentStatus.paid
        elif event_type in {"checkout.session.expired", "payment_intent.payment_failed"}:
            status = PaymentStatus.failed
        else:
            # An event we don't act on is still a delivery worth acknowledging,
            # or Stripe keeps resending it.
            status = PaymentStatus.pending

        provider_payment_id = obj.get("payment_intent") or obj.get("id")
        return WebhookResult(
            status=status,
            provider_payment_id=str(provider_payment_id) if provider_payment_id else None,
            response_body='{"received": true}',
            response_content_type="application/json",
        )
