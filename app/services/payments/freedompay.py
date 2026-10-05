"""Freedom Pay (бывший PayBox) — Казахстан, Узбекистан, Кыргызстан, Россия.

The one gateway on this list that takes tenge, sum, som and roubles from the
same merchant account, which is why it is here: for a seller in Kazakhstan
it is usually the shortest path to accepting local cards.

Protocol, all of it: form-encoded POST to `init_payment.php`, XML back with
`pg_redirect_url`. Every request and every callback carries `pg_sig` —

    md5( script_name ; values of all other params sorted by key ; secret )

joined by semicolons. `script_name` is the last path segment of the URL
being signed, which for the callback is *our* address, not theirs — so the
callback signs against "freedompay", the tail of `/webhook/pay/freedompay`.

Written against the published PayBox signature implementation
(github.com/boomfly/meteor-paybox, src/signature.coffee) rather than from
memory.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid

import defusedxml.ElementTree as ET
import httpx

from app.config import get_settings
from app.models.payment import PaymentStatus
from app.services.payments.base import (
    Checkout,
    CheckoutRequest,
    CredentialField,
    PaymentRef,
    ProviderDefaults,
    ProviderError,
    RecurringMode,
    RecurringSetup,
    WebhookResult,
    minor_to_major,
    same_currency,
)

# Адрес из официальной документации Freedom Pay (docs.freedompay.kz). Для
# мерчантов в Кыргызстане у них отдельный хост api.freedompay.kg.
_BASE = "https://api.freedompay.kz"
_BASE_KG = "https://api.freedompay.kg"
_BASE_UZ = "https://api.freedompay.uz"
#: The tail of our own callback address — what Freedom Pay signs its
#: notification with. Must match the route in `payments.py`.
logger = logging.getLogger(__name__)

_CALLBACK_SCRIPT = "freedompay"
#: Списание по сохранённому профилю — `POST /g2g/recurrent` (официальная схема Gateway API → Sync API →
#: Purchase → Recurrent). Подпись строится от ПОСЛЕДНЕГО сегмента адреса: `recurrent`. Раньше здесь стояло
#: легаси-имя `make_recurring_payment`.
_RECURRING_PATH = "g2g/recurrent"
_RECURRING_SCRIPT = "recurrent"
#: How long a saved profile stays chargeable — in MONTHS, not days: Freedom
#: Pay's documentation gives `pg_recurring_lifetime` as 1..156 (months, up to
#: 13 years). It used to be sent as 730 "days", which is outside the allowed
#: range and risked a refusal of the very first subscription payment. Two years,
#: capped by the card's own expiry on their side.
_RECURRING_LIFETIME_MONTHS = 24
#: Error codes that mean "this profile will never work again", as opposed to
#: "the bank said no this time".
_DEAD_PROFILE = {"9011", "11070"}


def _sign(script: str, params: dict[str, str], secret: str) -> str:
    """md5 over script name, every value sorted by key, and the secret."""
    parts = [script]
    parts += [str(params[key]) for key in sorted(params) if key != "pg_sig"]
    parts.append(secret)
    return hashlib.md5(";".join(parts).encode(), usedforsecurity=False).hexdigest()


class FreedomPayProvider(ProviderDefaults):
    #: Адрес уведомления уходит в самом счёте — вписывать его в кабинете не нужно.
    sends_own_callback_url = True
    slug = "freedompay"
    title = "Freedom Pay"
    hint = (
        "Merchant ID и секретный ключ — в кабинете Freedom Pay, раздел «Настройки магазина». "
        "Там же в поле «Post-запрос при результате платежа» укажи адрес, который мы покажем ниже. "
        "Принимает карты Казахстана, Узбекистана, Кыргызстана и России."
    )
    currencies = ("KZT", "UZS", "KGS", "RUB", "USD", "EUR")
    region = "ca"
    # Рекуррент: первый платёж с pg_recurring_start=1 создаёт профиль, его
    # номер приходит на ResultURL, дальше POST на /g2g/recurrent.
    # Имя скрипта — без .php (легаси-форма с .php осталась у Platron и
    # старого Paybox), и оно же идёт в подпись как последний сегмент URL.
    recurring = RecurringMode.token
    credential_fields = (
        CredentialField("merchant_id", "Merchant ID", "номер магазина из кабинета", secret=False),
        CredentialField("secret_key", "Секретный ключ", "секретный ключ мерчанта"),
        CredentialField("country", "Страна магазина", "kz (по умолчанию), uz — Узбекистан или kg — Кыргызстан", secret=False, required=False),
    )

    @staticmethod
    def _base(credentials: dict[str, str]) -> str:
        """Хост API: у Казахстана, Узбекистана и Кыргызстана они разные (тот же протокол и подпись)."""
        country = (credentials.get("country") or "").strip().lower()
        return {"kg": _BASE_KG, "uz": _BASE_UZ}.get(country, _BASE)

    @staticmethod
    def _keys(credentials: dict[str, str]) -> tuple[str, str]:
        merchant = (credentials.get("merchant_id") or "").strip()
        secret = (credentials.get("secret_key") or "").strip()
        if not merchant or not secret:
            raise ProviderError("Freedom Pay: не заполнены Merchant ID или секретный ключ")
        return merchant, secret

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        merchant, secret = self._keys(request.credentials)
        base = get_settings().public_base_url.rstrip("/")

        params = {
            "pg_merchant_id": merchant,
            "pg_order_id": str(request.payment_id),
            "pg_amount": minor_to_major(request.amount_minor),
            "pg_currency": request.currency.upper(),
            "pg_description": (request.description or "Оплата")[:255],
            "pg_result_url": f"{base}/webhook/pay/{_CALLBACK_SCRIPT}",
            # Freedom Pay only POSTs the result when told to; without this it
            # would wait for the buyer's browser to come back, and a buyer
            # who closes the tab would never be delivered to.
            "pg_request_method": "POST",
            "pg_success_url": request.return_url,
            "pg_failure_url": request.return_url,
            "pg_language": "ru",
            # Any unique value; it only exists to make the signature differ
            # between two otherwise identical requests.
            "pg_salt": secrets.token_hex(8),
        }
        if request.extra.get("subscription"):
            params["pg_recurring_start"] = "1"
            # How long the profile stays chargeable, in months (per the provider docs: 1..156; units still worth confirming). Asked for a
            # good deal longer than one period so a subscription is not
            # silently cut off at the first renewal; Freedom Pay caps it at
            # the card's own expiry anyway.
            params["pg_recurring_lifetime"] = str(_RECURRING_LIFETIME_MONTHS)
        if request.is_test:
            params["pg_testing_mode"] = "1"
        params["pg_sig"] = _sign("init_payment.php", params, secret)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self._base(request.credentials)}/init_payment.php", data=params)
        if response.status_code >= 400:
            raise ProviderError(f"Freedom Pay: HTTP {response.status_code}")

        payload = _parse_xml(response.text)
        if (payload.get("pg_status") or "").lower() == "error":
            detail = payload.get("pg_error_description") or payload.get("pg_error_code") or "отказ"
            raise ProviderError(f"Freedom Pay: {detail}")
        url = payload.get("pg_redirect_url")
        if not url:
            raise ProviderError("Freedom Pay: ответ без ссылки на оплату")

        return Checkout(url=url, provider_payment_id=payload.get("pg_payment_id"))

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        try:
            return PaymentRef(payment_id=uuid.UUID((form.get("pg_order_id") or "").strip()))
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
        _merchant, secret = self._keys(credentials)

        received = (form.get("pg_sig") or "").strip().lower()
        if not received or not hmac.compare_digest(received, _sign(_CALLBACK_SCRIPT, form, secret)):
            raise ProviderError("Freedom Pay: подпись уведомления не совпала")

        remote_id = (form.get("pg_payment_id") or "").strip() or None
        result = (form.get("pg_result") or "").strip()

        # Повтор уведомления (касса повторяет, пока не получит ответ) получает ТОТ ЖЕ
        # ответ байт в байт: пересчитанный ответ с новой солью — уже не тот, что мы дали.
        replies = dict((meta or {}).get("freedompay_replies") or {})
        saved = replies.get(remote_id or "")
        if saved:
            return WebhookResult(
                status=PaymentStatus(saved["status"]),
                provider_payment_id=remote_id,
                response_body=saved["xml"],
                response_content_type="application/xml",
            )

        def answer(status: PaymentStatus, xml: str, **notes) -> WebhookResult:
            if remote_id:
                replies[remote_id] = {"status": status.value, "xml": xml}
            return WebhookResult(
                status=status,
                provider_payment_id=remote_id,
                response_body=xml,
                response_content_type="application/xml",
                meta={"freedompay_replies": replies, **notes},
            )

        if result != "1":
            # 0 means the payment failed; anything else is not a settlement.
            return answer(PaymentStatus.failed if result == "0" else PaymentStatus.pending, _ack(secret, "ok"))

        amount = (form.get("pg_amount") or "").strip()
        try:
            mismatch = abs(float(amount.replace(",", ".")) - amount_minor / 100) > 0.009
        except ValueError:
            mismatch = True
        problem = ""
        if mismatch:
            problem = f"сумма не совпадает (пришло {amount})"
        elif (meta or {}).get("_status") == "paid":
            problem = "заказ уже оплачен другим платежом"
        else:
            try:
                same_currency(self.title, form.get("pg_currency"), currency)
            except ProviderError as exc:
                problem = str(exc)

        if problem:
            if (form.get("pg_can_reject") or "").strip() == "1":
                # Платёж ещё можно отклонить: касса вернёт деньги покупателю сама.
                logger.warning("Freedom Pay: платёж %s отклонён: %s", remote_id, problem)
                return answer(PaymentStatus.pending, _ack(secret, "rejected", problem))
            # Отклонить нельзя: принимаем ответом ok, но товар не выдаём — деньги вернуть вручную.
            logger.error("Freedom Pay: безотзывный платёж %s не сошёлся (%s), нужен ручной возврат", remote_id, problem)
            return answer(PaymentStatus.pending, _ack(secret, "ok"), freedompay_manual_refund=problem)

        notes = {}
        # The profile only ever arrives here. Both spellings are accepted:
        # the docs name the field `pg_recurring_profile_id` on the result and
        # `pg_recurring_profile` on the charge, and it costs nothing to read
        # whichever one turns up.
        profile = (form.get("pg_recurring_profile_id") or form.get("pg_recurring_profile") or "").strip()
        if profile:
            notes["freedompay_recurring_profile"] = profile
        # Freedom Pay retries until it gets a signed "ok" back.
        return answer(PaymentStatus.paid, _ack(secret, "ok"), **notes)

    def recurring_setup(self, settled: dict) -> RecurringSetup | None:
        profile = (settled or {}).get("freedompay_recurring_profile")
        return RecurringSetup(token=str(profile)) if profile else None

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
        """Ask Freedom Pay to take the next period off the saved profile.

        Returns `pending`, never `paid` — the same shape as Robokassa and for
        the same reason. `pg_status=ok` here means the payment was *created*
        (the response carries a fresh `pg_payment_id`); whether the card
        actually paid arrives later on `pg_result_url`, as an ordinary
        `pg_result=0/1` callback that settles this very payment. A declined
        card is not visible in this XML at all, so treating "ok" as money
        would hand over a month of access for nothing.
        """
        merchant, secret = self._keys(credentials)
        base = get_settings().public_base_url.rstrip("/")

        params = {
            "pg_merchant_id": merchant,
            "pg_recurring_profile": str(setup.token),
            "pg_order_id": str(payment_id),
            "pg_amount": minor_to_major(amount_minor),
            "pg_currency": currency.upper(),
            "pg_description": (description or "Продление подписки")[:255],
            "pg_result_url": f"{base}/webhook/pay/{_CALLBACK_SCRIPT}",
            "pg_request_method": "POST",
            "pg_salt": secrets.token_hex(8),
        }
        # Подпись берёт последний сегмент адреса — `recurrent`, а не весь путь.
        params["pg_sig"] = _sign(_RECURRING_SCRIPT, params, secret)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self._base(credentials)}/{_RECURRING_PATH}", data=params)
        if response.status_code >= 400:
            raise ProviderError(f"Freedom Pay: HTTP {response.status_code}")

        payload = _parse_xml(response.text)
        if (payload.get("pg_status") or "").lower() != "ok":
            code = (payload.get("pg_error_code") or "").strip()
            detail = payload.get("pg_error_description") or code or "отказ"
            if code in _DEAD_PROFILE:
                # The saved profile is gone — retrying cannot fix it, and the
                # subscription layer falls back to asking for a fresh payment.
                raise ProviderError(f"Freedom Pay: привязка карты больше не действует ({detail})")
            raise ProviderError(f"Freedom Pay: {detail}")

        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=payload.get("pg_payment_id"))


def _ack(secret: str, status: str, description: str = "") -> str:
    """The acknowledgement Freedom Pay wants: an XML response signed the same
    way, with our own script name."""
    params = {"pg_status": status, "pg_salt": secrets.token_hex(8)}
    if description:
        params["pg_description"] = description
    params["pg_sig"] = _sign(_CALLBACK_SCRIPT, params, secret)
    body = "".join(f"<{key}>{value}</{key}>" for key, value in params.items())
    return f"<?xml version='1.0' encoding='utf-8'?><response>{body}</response>"


def _parse_xml(text: str) -> dict[str, str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ProviderError("Freedom Pay: непонятный ответ") from exc
    return {child.tag: (child.text or "") for child in root}
