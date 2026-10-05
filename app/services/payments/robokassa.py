"""Robokassa — a signed redirect link, no API call needed to start.

Checkout is a plain URL whose SignatureValue is md5 of
"MerchantLogin:OutSum:InvId:Password1"; the ResultURL callback carries
"OutSum:InvId:Password2" and expects the literal body "OK{InvId}" back,
retrying until it gets one.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from urllib.parse import quote_plus, urlencode

import defusedxml.ElementTree as ET
import httpx

from app.models.payment import PaymentStatus
from app.services.payments.base import (
    Checkout,
    CheckoutRequest,
    CredentialField,
    PaymentRef,
    ProviderDefaults,
    ProviderError,
    Receipt,
    RecurringMode,
    RecurringSetup,
    WebhookResult,
    minor_to_major,
    receipt_from_credentials,
)

_CHECKOUT_URL = "https://auth.robokassa.ru/Merchant/Index.aspx"
_RECURRING_URL = "https://auth.robokassa.ru/Merchant/Recurring"
_STATE_URL = "https://auth.robokassa.ru/Merchant/WebService/Service.asmx/OpStateExt"


#: Алгоритм хэша выбирается в технических настройках магазина (по умолчанию MD5), и подпись надо считать
#: тем же: иначе касса ответит ошибкой 29 на КАЖДЫЙ платёж.
_ALGOS = {"md5", "sha1", "sha256", "sha384", "sha512", "ripemd160"}


def _algo(credentials: dict[str, str]) -> str:
    name = (credentials.get("hash_algo") or "md5").strip().lower().replace("-", "")
    if name not in _ALGOS:
        raise ProviderError(f"Robokassa: неизвестный алгоритм хэша «{name}». Допустимо: {', '.join(sorted(_ALGOS))}")
    return name


def _digest(algo: str, text: str) -> str:
    try:
        return hashlib.new(algo, text.encode()).hexdigest()
    except ValueError as exc:  # ripemd160 есть не в каждой сборке OpenSSL
        raise ProviderError(f"Robokassa: алгоритм {algo} не поддерживается на этом сервере") from exc


def _plain(text: str) -> str:
    """Описание заказа — до 100 знаков и «без спецсимволов» (документация)."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s.,\-—!?()№#:/+]", " ", text or "")).strip()


def receipt_robokassa(r: Receipt) -> dict:
    """sum позиции = итог по позиции в рублях."""
    return {
        "sno": r.tax_system.value,
        "items": [
            {
                "name": i.name,
                "quantity": float(i.qty),
                "sum": float(i.total),
                "tax": i.vat.value,
                "payment_method": i.method.value,
                "payment_object": i.obj.value,
            }
            for i in r.items
        ],
    }


class RobokassaProvider(ProviderDefaults):
    slug = "robokassa"
    title = "Robokassa"
    hint = (
        "Логин магазина и оба пароля — в личном кабинете Robokassa, раздел «Технические настройки». "
        "Там же укажи Result URL, который мы покажем ниже, и метод отправки POST. Счёт выставляется в валюте твоего магазина Robokassa — для тенге удобнее Freedom Pay, ioka или CloudPayments."
    )
    currencies = ("RUB",)
    region = "ru"
    # Периодические платежи: первая оплата уходит с Recurring=true, дальше
    # POST на /Merchant/Recurring с номером первого счёта в PreviousInvoiceID.
    # Ответ «OK<InvId>» означает «операция создана», а не «деньги списаны» —
    # результат приходит обычным уведомлением на ResultURL, поэтому списание
    # возвращает pending, а не paid. Имена полей и эндпоинт сверены с
    # github.com/mikhail5545/go-robokassa-sdk (RecurringPaymentRequest:
    # MerchantLogin / InvoiceID / PreviousInvoiceID / OutSum / Description)
    # и с описанием «Периодические платежи» в документации Robokassa.
    recurring = RecurringMode.token
    supports_status_check = True
    credential_fields = (
        CredentialField("merchant_login", "Идентификатор магазина", "MerchantLogin из кабинета", secret=False),
        CredentialField("password1", "Пароль #1", "Используется для подписи ссылки на оплату"),
        CredentialField("password2", "Пароль #2", "Используется для проверки уведомления об оплате"),
        CredentialField(
            "test_password1", "Тестовый пароль #1", "нужен для тестового режима: отдельные тестовые пароли в кабинете", required=False),
        CredentialField("test_password2", "Тестовый пароль #2", "нужен для тестового режима", required=False),
        CredentialField(
            "hash_algo", "Алгоритм хэша",
            "как в технических настройках магазина: md5 (по умолчанию), sha1, sha256, sha384, sha512, ripemd160",
            secret=False, required=False,
        ),
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

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        login = (request.credentials.get("merchant_login") or "").strip()
        password1 = (request.credentials.get("password1") or "").strip()
        if not login or not password1:
            raise ProviderError("Robokassa: не заполнены идентификатор магазина или пароль #1")

        if request.is_test:
            # По документации Robokassa в тестовом режиме подпись считается ОТДЕЛЬНЫМИ
            # тестовыми паролями (алгоритм тот же), а в запросе обязателен IsTest=1.
            password1 = (request.credentials.get("test_password1") or "").strip()
            if not password1:
                raise ProviderError(
                    "Robokassa: для тестового режима заполни тестовые пароли #1 и #2 (или выключи тестовый режим)"
                )

        out_sum = minor_to_major(request.amount_minor)
        # Чек входит в подпись: MerchantLogin:OutSum:InvId:Receipt:Пароль1. В подпись и в
        # ссылку идёт значение, один раз закодированное urlencode (как PHP urlencode); сама
        # ссылка кодирует его ещё раз — так в GET-адресе и требует касса (один раз → ошибка
        # 29, проверено в живую сторонней библиотекой).
        receipt = receipt_from_credentials(
            request.credentials, request.description, request.amount_minor,
            buyer_email=request.buyer_email, buyer_phone=request.buyer_phone,
        )
        receipt_once = ""
        parts = [login, out_sum, str(request.invoice_no)]
        if receipt:
            raw = json.dumps(receipt_robokassa(receipt), ensure_ascii=False, separators=(",", ":"))
            receipt_once = quote_plus(raw)
            parts.append(receipt_once)
        parts.append(password1)
        signature = _digest(_algo(request.credentials), ":".join(parts))

        params = {
            "MerchantLogin": login,
            "OutSum": out_sum,
            "InvId": str(request.invoice_no),
            "Description": _plain(request.description)[:100] or "Оплата",
            "SignatureValue": signature,
            "Culture": "ru",
            "Encoding": "utf-8",
            # `SuccessURL2` здесь не передаётся: по документации Robokassa такие
            # модификаторы входят в строку подписи, и ошибка в её составе ломает ВСЕ платежи.
            # Адрес возврата покупателя задаётся в кабинете (Success URL).
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
        if receipt_once:
            params["Receipt"] = receipt_once
        if request.extra.get("subscription"):
            # Without this the card is not remembered and every later
            # /Merchant/Recurring call is refused.
            params["Recurring"] = "true"
        if request.is_test:
            params["IsTest"] = "1"

        return Checkout(
            url=f"{_CHECKOUT_URL}?{urlencode(params)}",
            provider_payment_id=str(request.invoice_no),
            # Запоминаем режим платежа: уведомление проверяется паролем именно этого режима.
            meta={"robokassa_test": bool(request.is_test)},
        )

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
        # Пароль выбирается по режиму ЭТОГО платежа, а не перебирается: иначе тестовая
        # подпись могла бы провести боевой заказ.
        is_test = bool((meta or {}).get("robokassa_test"))
        password2 = (credentials.get("test_password2" if is_test else "password2") or "").strip()
        if not password2:
            raise ProviderError("Robokassa: не заполнен пароль #2" + (" (тестовый)" if is_test else ""))
        if (form.get("IsTest") or "").strip() == "1" and not is_test:
            raise ProviderError("Robokassa: тестовое уведомление для боевого платежа")

        out_sum = (form.get("OutSum") or "").strip()
        received = (form.get("SignatureValue") or "").strip().lower()
        # Пользовательские параметры Shp_* (если они пришли) входят в подпись после пароля, по алфавиту.
        shp = "".join(f":{key}={form[key]}" for key in sorted(k for k in form if k.startswith("Shp_")))
        expected = _digest(_algo(credentials), f"{out_sum}:{invoice_no}:{password2}{shp}")
        if not received or not hmac.compare_digest(received, expected):
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
            # Robokassa has no card token of its own: the handle for every
            # later charge is the invoice number that started the series.
            meta={"robokassa_first_invoice": str(invoice_no)},
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
        """`OpStateExt`: состояние операции по номеру счёта (подпись `MerchantLogin:InvoiceID:Пароль#2`).

        Работает только для боевых платежей — тестовые (`IsTest=1`) метод не отдаёт."""
        if (meta or {}).get("robokassa_test"):
            raise ProviderError("Robokassa: статус тестового платежа по API недоступен — дождись уведомления")
        login = (credentials.get("merchant_login") or "").strip()
        password2 = (credentials.get("password2") or "").strip()
        if not login or not password2:
            raise ProviderError("Robokassa: не заполнены идентификатор магазина или пароль #2")
        signature = _digest(_algo(credentials), f"{login}:{invoice_no}:{password2}")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                _STATE_URL, params={"MerchantLogin": login, "InvoiceID": str(invoice_no), "Signature": signature}
            )
        if response.status_code >= 400:
            raise ProviderError(f"Robokassa: HTTP {response.status_code}")
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            raise ProviderError("Robokassa: непонятный ответ на запрос статуса") from exc

        def find(path: str) -> str:
            node = root.find(f".//{{*}}{path.replace('/', '/{*}')}")
            return (node.text or "").strip() if node is not None and node.text else ""

        result = find("Result/Code")
        if result == "3":
            # Операция создаётся, когда покупатель подтвердил реквизиты: до этого её просто нет.
            return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(invoice_no))
        if result != "0":
            raise ProviderError(f"Robokassa: статус не получен (код {result or '?'}: {find('Result/Description')})")

        state = find("State/Code")
        if state == "100":
            out_sum = find("Info/OutSum")
            if out_sum:
                try:
                    if abs(float(out_sum.replace(",", ".")) - amount_minor / 100) > 0.009:
                        raise ProviderError(f"Robokassa: сумма не совпадает (в операции {out_sum})")
                except ValueError:
                    pass
            return WebhookResult(
                status=PaymentStatus.paid,
                provider_payment_id=str(invoice_no),
                meta={"robokassa_first_invoice": str(invoice_no)},
            )
        if state == "10":
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=str(invoice_no))
        if state == "60":
            return WebhookResult(status=PaymentStatus.refunded, provider_payment_id=str(invoice_no))
        # 5 — не подтверждена, 20 — холд, 50 — зачисляется, 80 — приостановлена проверкой: ещё не деньги.
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(invoice_no))

    def recurring_setup(self, settled: dict) -> RecurringSetup | None:
        first = (settled or {}).get("robokassa_first_invoice")
        return RecurringSetup(token=str(first)) if first else None

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
        """Ask Robokassa to take the next period off the remembered card.

        Returns `pending`, never `paid`, even on a completely successful
        call: Robokassa answers "OK<InvId>" to say the operation was
        *created*, and whether the money actually moved arrives later on
        ResultURL like any other payment. Treating the acknowledgement as a
        settlement would hand over a month of access for a charge that may
        still be declined.
        """
        login = (credentials.get("merchant_login") or "").strip()
        password1 = (credentials.get("password1") or "").strip()
        if not login or not password1:
            raise ProviderError("Robokassa: не заполнены идентификатор магазина или пароль #1")
        if invoice_no is None:
            raise ProviderError("Robokassa: у повторного платежа нет номера счёта")

        out_sum = minor_to_major(amount_minor)
        # Same composition as a first payment — the recurring call is signed
        # with its *own* invoice number, not the previous one.
        # Чек продления — тот же формат, что у первого платежа; входит в подпись между номером счёта и паролем.
        receipt = receipt_from_credentials(
            credentials, description or "Продление подписки", amount_minor,
            buyer_email=credentials.get("_buyer_email"), buyer_phone=credentials.get("_buyer_phone"),
        )
        parts = [login, out_sum, str(invoice_no)]
        receipt_once = ""
        if receipt:
            receipt_once = quote_plus(json.dumps(receipt_robokassa(receipt), ensure_ascii=False, separators=(",", ":")))
            parts.append(receipt_once)
        parts.append(password1)
        signature = _digest(_algo(credentials), ":".join(parts))
        body = {
            "MerchantLogin": login,
            "InvoiceID": str(invoice_no),
            "PreviousInvoiceID": str(setup.token),
            "OutSum": out_sum,
            "Description": _plain(description or "Продление подписки")[:100] or "Продление подписки",
            "SignatureValue": signature,
        }
        if receipt_once:
            body["Receipt"] = receipt_once

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(_RECURRING_URL, data=body)
        if response.status_code >= 400:
            raise ProviderError(f"Robokassa: HTTP {response.status_code}")
        answer = (response.text or "").strip()
        if not answer.upper().startswith("OK"):
            raise ProviderError(f"Robokassa: {answer[:200] or 'отказ'}")

        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(invoice_no))
