"""Prodamus — a signed payform link, with a signed callback back.

The signature is the whole integration, and it is exacting: strip the
signature key, sort every level of the structure by key, render every scalar
as a string, JSON-encode without escaping unicode or slashes and without
spaces, then HMAC-SHA256 with the shop's secret. Both directions use it —
the outgoing link carries `signature`, the callback carries `Sign` — so the
same serialiser has to produce byte-identical output from a dict we built
ourselves and from a form body Prodamus posted at us. That round trip is
the part worth testing, and it is (see tests/test_providers.py).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from urllib.parse import parse_qsl, urlencode

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

_KEY_PART_RE = re.compile(r"\[([^\[\]]*)\]")


def _normalise(value):
    """PHP's loose scalars, spelled out: booleans become "1"/"0", null the
    empty string, numbers their decimal text."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return value


def _prepare(obj):
    if isinstance(obj, dict):
        return {key: _prepare(obj[key]) for key in sorted(obj)}
    if isinstance(obj, list):
        return [_prepare(item) for item in obj]
    return _normalise(obj)


def sign(data: dict, secret: str) -> str:
    payload = {k: v for k, v in data.items() if k not in ("signature", "sign")}
    encoded = json.dumps(_prepare(payload), ensure_ascii=False, separators=(",", ":"))
    return hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()


def _listify(node):
    """PHP arrays keyed 0,1,2… JSON-encode as arrays, not objects — and the
    signature is computed over that JSON, so the distinction is not
    cosmetic."""
    if isinstance(node, dict):
        converted = {key: _listify(value) for key, value in node.items()}
        keys = list(converted)
        if keys and all(k.isdigit() for k in keys) and sorted(int(k) for k in keys) == list(range(len(keys))):
            return [converted[str(i)] for i in range(len(keys))]
        return converted
    return node


def parse_form(raw_body: str) -> dict:
    """`products[0][name]=Гайд&sum=990` → nested dict/list, the way PHP's
    own form parser would see it. This is the single most common reason a
    Prodamus signature check fails, so it is done explicitly rather than
    left to whatever a framework guessed."""
    result: dict = {}
    for key, value in parse_qsl(raw_body, keep_blank_values=True):
        head, _, rest = key.partition("[")
        path = [head] + _KEY_PART_RE.findall(f"[{rest}" if rest else "")
        node = result
        for part in path[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):  # a scalar already sits here — malformed input
                raise ProviderError("Prodamus: не удалось разобрать тело уведомления")
        node[path[-1]] = value
    return _listify(result)


def _flatten(data: dict) -> list[tuple[str, str]]:
    """The inverse: nested structure → `products[0][name]` query pairs."""
    pairs: list[tuple[str, str]] = []

    def walk(prefix: str, node):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(f"{prefix}[{key}]" if prefix else str(key), value)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(f"{prefix}[{index}]", value)
        else:
            pairs.append((prefix, _normalise(node)))

    walk("", data)
    return pairs


# Everything else Prodamus may report — "pending", "hold", a blank — means
# the payment is still in play and must not be written off.
_FAILED = {"failed", "fail", "canceled", "cancelled", "rejected", "error", "expired"}


class ProdamusProvider(ProviderDefaults):
    slug = "prodamus"
    title = "Prodamus"
    hint = (
        "Домен вида myshop.payform.ru и секретный ключ — в личном кабинете Prodamus, раздел «Настройки → "
        "Интеграции». Для тестов выдают демо-магазин demo.payform.ru со своим ключом. Адрес уведомления "
        "(urlNotification) мы подставляем сами, отдельно в кабинете его прописывать не нужно."
    )
    currencies = ("RUB",)
    credential_fields = (
        CredentialField("shop_domain", "Домен платёжной формы", "myshop.payform.ru", secret=False),
        CredentialField("secret_key", "Секретный ключ", "из раздела «Интеграции» в кабинете"),
    )

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        domain = (request.credentials.get("shop_domain") or "").strip().rstrip("/")
        secret = (request.credentials.get("secret_key") or "").strip()
        if not domain or not secret:
            raise ProviderError("Prodamus: не заполнен домен формы или секретный ключ")
        domain = domain.removeprefix("https://").removeprefix("http://")

        from app.config import get_settings

        base = get_settings().public_base_url.rstrip("/")
        data = {
            # Our payment id travels as order_id and comes straight back in
            # the callback — no mapping table needed.
            "order_id": str(request.payment_id),
            "products": [
                {
                    "name": request.description[:255] or "Оплата",
                    "price": minor_to_major(request.amount_minor),
                    "quantity": "1",
                }
            ],
            "urlNotification": f"{base}/webhook/pay/prodamus",
            "urlSuccess": request.return_url,
            "urlReturn": request.return_url,
            "do": "pay",
        }
        data["signature"] = sign(data, secret)
        return Checkout(url=f"https://{domain}/?{urlencode(_flatten(data))}")

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        try:
            data = parse_form(raw_body.decode("utf-8", "replace"))
        except ProviderError:
            return PaymentRef()
        try:
            return PaymentRef(payment_id=uuid.UUID(str(data.get("order_id", ""))))
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
        secret = (credentials.get("secret_key") or "").strip()
        if not secret:
            raise ProviderError("Prodamus: не заполнен секретный ключ")

        received = (headers.get("sign") or "").strip().lower()
        if not received:
            raise ProviderError("Prodamus: уведомление без заголовка Sign")

        data = parse_form(raw_body.decode("utf-8", "replace"))
        if not hmac.compare_digest(sign(data, secret), received):
            raise ProviderError("Prodamus: подпись уведомления не совпала")

        status = str(data.get("payment_status", "")).lower()
        if status != "success":
            # Not an error: a failed attempt is a legitimate notification.
            # "Anything non-empty is a failure" used to be the rule, which
            # turned an in-progress notification into a permanently failed
            # payment — and a failed payment is never delivered.
            return WebhookResult(
                status=PaymentStatus.failed if status in _FAILED else PaymentStatus.pending,
                provider_payment_id=str(data.get("order_num") or "") or None,
                response_body="success",
            )

        paid = str(data.get("sum", "")).replace(",", ".")
        if paid and abs(float(paid) - amount_minor / 100) > 0.009:
            raise ProviderError(f"Prodamus: сумма не совпадает (пришло {paid})")

        return WebhookResult(
            status=PaymentStatus.paid,
            provider_payment_id=str(data.get("order_num") or "") or None,
            response_body="success",
        )
