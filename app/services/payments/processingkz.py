"""Processing.kz (CNP Processing GmbH) — Казахстан.

The oldest protocol in this project and the only SOAP one: an Axis2 service
at `payment.processinggmbh.ch`, three operations we care about —
`startTransaction`, `getTransactionStatus`, `completeTransaction`.

Two things make it unlike every other adapter here.

**There is no callback and no signature.** Nothing is posted back to us and
nothing is signed; the only credential is the merchant id. So this adapter
never trusts an incoming request — it only ever *asks*: the buyer taps «Я
оплатил» and we read the transaction's status from the gateway over TLS.
`uses_callback` is False for exactly that reason.

**Payment is two-stage by default.** After the buyer pays, the transaction
sits at `AUTHORISED` — the money is *blocked* on the card, not taken. It
becomes `PAID` only after `completeTransaction`. Delivering on AUTHORISED
would hand over the goods against a hold that later expires, so this
adapter captures first and re-reads, and calls nothing paid until the
gateway itself says `PAID`.

Written against the WSDL as published in github.com/pashagray/processing_kz
(`spec/CNPMerchantWebService.wsdl`), that gem's own live-run specs — which
are where the status names come from — and CNP's own generated PHP client
in github.com/andrew2net/store, which is where the production endpoint
comes from. Not from memory.
"""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from xml.sax.saxutils import escape

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

_PROD = "https://payment.processinggmbh.ch/CNPMerchantWebServices/services/CNPMerchantWebService"
_TEST = "https://test.processing.kz/CNPMerchantWebServices/services/CNPMerchantWebService"

_SOAP_ENV = "http://www.w3.org/2003/05/soap-envelope"
#: The request wrappers (startTransaction, getTransactionStatus, …).
_NS_WS = "http://kz.processing.cnp.merchant_ws/xsd"
#: TransactionDetails and GoodsItem — a different schema, and the WSDL sets
#: elementFormDefault="qualified" everywhere, so their children carry it.
_NS_BEANS = "http://beans.common.cnp.processing.kz/xsd"

#: ISO 4217 numeric codes, which is what `currencyCode` wants. 398 is the one
#: the reference states outright; the rest follow the same standard. A wrong
#: code here is refused by `startTransaction` before any money moves, so it
#: fails loudly at checkout rather than quietly at settlement.
_NUMERIC = {"KZT": 398, "RUB": 643, "USD": 840, "EUR": 978}

#: Status names as the reference's live runs against the gateway recorded
#: them. Anything not listed is treated as "still open" rather than guessed.
_PAID = "PAID"
_AUTHORISED = "AUTHORISED"
_FAILED = {"REVERSED", "DECLINED", "CANCELLED", "CANCELED", "FAILED", "EXPIRED"}


class ProcessingKzProvider(ProviderDefaults):
    slug = "processingkz"
    title = "Processing.kz"
    hint = (
        "Merchant ID (и Terminal ID, если банк его выдал) — из договора с банком: Processing.kz "
        "подключается через банк-эквайер. Уведомлений этот шлюз не присылает, поэтому бот сам "
        "спрашивает статус, когда покупатель жмёт «Я оплатил» — адрес в кабинете указывать не нужно."
    )
    currencies = ("KZT", "RUB", "USD", "EUR")
    supports_status_check = True
    # Nothing is ever posted to `/webhook/pay/processingkz`: the gateway has
    # no notification of its own, so the settings form has no address to show.
    uses_callback = False
    credential_fields = (
        CredentialField("merchant_id", "Merchant ID", "15 цифр из договора с банком", secret=False),
        CredentialField("terminal_id", "Terminal ID", "если банк выдал отдельный терминал", secret=False),
    )

    @staticmethod
    def _merchant(credentials: dict[str, str]) -> str:
        merchant = (credentials.get("merchant_id") or "").strip()
        if not merchant:
            raise ProviderError("Processing.kz: не заполнен Merchant ID")
        return merchant

    @staticmethod
    def _endpoint(is_test: bool) -> str:
        return _TEST if is_test else _PROD

    async def _call(self, endpoint: str, operation: str, body: str) -> ET.Element:
        envelope = (
            '<?xml version="1.0" encoding="utf-8"?>'
            f'<soap:Envelope xmlns:soap="{_SOAP_ENV}" xmlns:ws="{_NS_WS}" xmlns:b="{_NS_BEANS}">'
            f"<soap:Body>{body}</soap:Body></soap:Envelope>"
        )
        async with httpx.AsyncClient(timeout=40) as client:
            response = await client.post(
                endpoint,
                content=envelope.encode("utf-8"),
                headers={
                    # SOAP 1.2 carries the action in the content type, and the
                    # WSDL names it `urn:<operation>`.
                    "Content-Type": f'application/soap+xml; charset=utf-8; action="urn:{operation}"',
                },
            )
        if response.status_code >= 400:
            raise ProviderError(f"Processing.kz: {_fault(response.text) or f'HTTP {response.status_code}'}")
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise ProviderError("Processing.kz: непонятный ответ шлюза") from exc

        fault = _find(root, "Fault")
        if fault is not None:
            raise ProviderError(f"Processing.kz: {_text(_find(fault, 'Text')) or 'ошибка шлюза'}")
        returned = _find(root, "return")
        if returned is None:
            raise ProviderError("Processing.kz: пустой ответ шлюза")
        return returned

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        merchant = self._merchant(request.credentials)
        terminal = (request.credentials.get("terminal_id") or "").strip()
        code = _NUMERIC.get(request.currency.upper())
        if code is None:
            raise ProviderError(f"Processing.kz: валюта {request.currency} не поддерживается")

        title = (request.description or "Оплата")[:255]
        # The gateway requires a goods list and adds it up itself, so the one
        # line has to be the whole order. Amounts are minor units — the same
        # tiyn/kopeck integers everything here is stored in.
        goods = (
            "<b:goodsList>"
            f"<b:amount>{request.amount_minor}</b:amount>"
            f"<b:currencyCode>{code}</b:currencyCode>"
            f"<b:merchantsGoodsID>{request.invoice_no}</b:merchantsGoodsID>"
            f"<b:nameOfGoods>{escape(title)}</b:nameOfGoods>"
            "</b:goodsList>"
        )
        details = [
            f"<b:currencyCode>{code}</b:currencyCode>",
            f"<b:description>{escape(title)}</b:description>",
            goods,
            "<b:languageCode>ru</b:languageCode>",
            f"<b:merchantId>{escape(merchant)}</b:merchantId>",
            f"<b:merchantLocalDateTime>{_now()}</b:merchantLocalDateTime>",
            f"<b:orderId>{request.invoice_no}</b:orderId>",
            f"<b:returnURL>{escape(request.return_url)}</b:returnURL>",
            f"<b:totalAmount>{request.amount_minor}</b:totalAmount>",
        ]
        if terminal:
            details.append(f"<b:terminalId>{escape(terminal)}</b:terminalId>")

        returned = await self._call(
            self._endpoint(request.is_test),
            "startTransaction",
            f"<ws:startTransaction><ws:transaction>{''.join(details)}</ws:transaction></ws:startTransaction>",
        )

        if _text(_find(returned, "success")) != "true":
            detail = _text(_find(returned, "errorDescription")) or "отказ"
            raise ProviderError(f"Processing.kz: {detail}")
        url = _text(_find(returned, "redirectURL"))
        reference = _text(_find(returned, "customerReference"))
        if not url or not reference:
            raise ProviderError("Processing.kz: ответ без ссылки на оплату")

        # customerReference is the only handle the gateway answers to later.
        # Which ledger it lives on is pinned here rather than re-read from the
        # shop's settings: a transaction started on the test endpoint stays
        # there even if the shop flips the switch while the buyer is paying.
        return Checkout(url=url, provider_payment_id=reference, meta={"is_test": request.is_test})

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
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
    ) -> WebhookResult:
        raise ProviderError("Processing.kz не присылает уведомлений — статус запрашиваем сами")

    async def check_status(
        self,
        *,
        credentials: dict[str, str],
        amount_minor: int,
        invoice_no: int,
        payment_id: uuid.UUID,
        provider_payment_id: str | None,
        meta: dict,
    ) -> WebhookResult:
        merchant = self._merchant(credentials)
        if not provider_payment_id:
            raise ProviderError("Processing.kz: платёж ещё не создан")
        # Which endpoint the transaction lives on is decided when it is
        # created; test and production keep separate ledgers.
        endpoint = self._endpoint(bool(meta.get("is_test")))

        status, amount = await self._read(endpoint, merchant, provider_payment_id)

        if status == _AUTHORISED:
            # Money held, not taken. Capture it, then believe only the second
            # read — `completeTransaction` returning true is its own claim,
            # and the ledger is what decides whether the shop gets paid.
            await self._complete(endpoint, merchant, provider_payment_id)
            status, amount = await self._read(endpoint, merchant, provider_payment_id)

        if status == _PAID:
            if amount is not None and amount != amount_minor:
                raise ProviderError(f"Processing.kz: сумма не совпадает (в шлюзе {amount})")
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=provider_payment_id)
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=provider_payment_id)
        # PENDING_CUSTOMER_INPUT and anything else unnamed: the buyer simply
        # has not finished yet.
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=provider_payment_id)

    async def _read(self, endpoint: str, merchant: str, reference: str) -> tuple[str, int | None]:
        returned = await self._call(
            endpoint,
            "getTransactionStatus",
            "<ws:getTransactionStatus>"
            f"<ws:merchantId>{escape(merchant)}</ws:merchantId>"
            f"<ws:referenceNr>{escape(reference)}</ws:referenceNr>"
            "</ws:getTransactionStatus>",
        )
        status = (_text(_find(returned, "transactionStatus")) or "").upper()
        settled = _amount(_text(_find(returned, "amountSettled")))
        authorised = _amount(_text(_find(returned, "amountAuthorised")))
        return status, settled if settled else authorised

    async def _complete(self, endpoint: str, merchant: str, reference: str) -> None:
        await self._call(
            endpoint,
            "completeTransaction",
            "<ws:completeTransaction>"
            f"<ws:merchantId>{escape(merchant)}</ws:merchantId>"
            f"<ws:referenceNr>{escape(reference)}</ws:referenceNr>"
            "<ws:transactionSuccess>true</ws:transactionSuccess>"
            "</ws:completeTransaction>",
        )


# ---------------------------------------------------------------- helpers


def _now() -> str:
    """`merchantLocalDateTime`, in the format the reference sends."""
    return datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S")


def _find(root: ET.Element, local_name: str) -> ET.Element | None:
    """Look an element up by its local name, ignoring namespaces.

    The service is Axis2 and spreads its answer over four namespaces with
    prefixes it chooses itself; matching on the local name is both simpler
    and steadier than pinning every one of them.
    """
    for element in root.iter():
        if element.tag.rpartition("}")[2] == local_name:
            return element
    return None


def _text(element: ET.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def _amount(raw: str) -> int | None:
    """Amounts come back as strings. The reference sends minor units, so a
    bare integer is read as such; a decimal point means the gateway answered
    in major units instead, and both have to mean the same money."""
    raw = raw.strip().replace(",", ".")
    if not raw:
        return None
    try:
        if "." in raw:
            return int(round(float(raw) * 100))
        return int(raw)
    except ValueError:
        return None


def _fault(text: str) -> str:
    try:
        return _text(_find(ET.fromstring(text), "Text"))
    except ET.ParseError:
        return ""
