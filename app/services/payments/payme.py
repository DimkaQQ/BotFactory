"""Payme (Paycom) — Узбекистан.

Unlike everything else here, Payme does not send a notification: it holds a
conversation. The same address is called with JSON-RPC methods —
`CheckPerformTransaction`, `CreateTransaction`, `PerformTransaction`,
`CheckTransaction`, `CancelTransaction` — and each answer has to be
consistent with the last one, including the exact millisecond timestamps we
reported before. That state lives in the payment's `meta`, which is why the
adapter reads `meta` in and hands a patch back out.

Authentication is HTTP Basic with the login `Paycom` and the cashbox key.
Errors are not HTTP errors: every reply is 200, with either `result` or
`error` in the body — see `error_body`.

Checkout is a link, not an API call:

    https://checkout.paycom.uz/<base64("m=…;ac.<key>=<order>;a=<tiyin>;c=<return>")>

Written against the published PaycomUz package (PyPI `PaycomUz`, module
`paycomuz`: `create_initialization`, `views.MerchantAPIView`, `status.py`)
rather than from memory.
"""

from __future__ import annotations

import base64
import binascii
import json
import time
import uuid

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

_CHECKOUT = "https://checkout.paycom.uz"

# Payme's error vocabulary, straight from the reference implementation.
_ERR_AUTH = -32504
_ERR_ORDER_NOT_FOUND = -31050
_ERR_INVALID_AMOUNT = -31001
_ERR_TRANSACTION_NOT_FOUND = -31003
_ERR_CANNOT_PERFORM = -31008

# Transaction states, likewise.
_STATE_CREATED = 1
_STATE_DONE = 2
_STATE_CANCELLED = -1
_STATE_CANCELLED_AFTER_DONE = -2

#: Payme abandons a transaction that has been open this long, and expects us
#: to refuse to create it.
_TRANSACTION_TTL_MS = 12 * 60 * 60 * 1000

_MESSAGES = {
    _ERR_ORDER_NOT_FOUND: {"uz": "Buyurtma topilmadi", "ru": "Заказ не найден", "en": "Order not found"},
    _ERR_INVALID_AMOUNT: {"uz": "Miqdori noto'g'ri", "ru": "Неверная сумма", "en": "Invalid amount"},
    _ERR_TRANSACTION_NOT_FOUND: {
        "uz": "Tranzaksiya topilmadi",
        "ru": "Транзакция не найдена",
        "en": "Transaction not found",
    },
    _ERR_CANNOT_PERFORM: {
        "uz": "Ushbu amalni bajarib bo'lmaydi",
        "ru": "Невозможно выполнить данную операцию",
        "en": "Unable to perform operation",
    },
    _ERR_AUTH: {
        "uz": "Foydalanuvchi mavjud emas",
        "ru": "Пользователь не существует",
        "en": "User does not exist",
    },
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ok(request_id, result: dict) -> str:
    return json.dumps({"result": result, "id": request_id}, ensure_ascii=False)


def _fail(request_id, code: int, data: str | None = None) -> str:
    error: dict = {"code": code, "message": _MESSAGES.get(code, {"ru": "Ошибка", "en": "Error", "uz": "Xato"})}
    if data:
        error["data"] = data
    return json.dumps({"error": error, "id": request_id}, ensure_ascii=False)


class PaymeRefusal(ProviderError):
    """A refusal Payme has to see as a JSON-RPC error rather than an HTTP one."""

    def __init__(self, body: str, reason: str):
        super().__init__(reason)
        self.body = body


class PaymeProvider(ProviderDefaults):
    slug = "payme"
    title = "Payme"
    hint = (
        "ID кассы и ключ — в кабинете Payme Business, «Настройки → Платежи». Ключ понадобится "
        "«для продакшена»; там же в поле Endpoint укажи адрес, который мы покажем ниже. "
        "Поле «Идентификатор заказа» оставь как order_id, если не менял его в кассе."
    )
    currencies = ("UZS",)
    credential_fields = (
        CredentialField("merchant_id", "ID кассы", "он же Merchant ID из кабинета", secret=False),
        CredentialField("key", "Ключ кассы", "тот, что для продакшена"),
        CredentialField(
            "account_field", "Поле заказа", "по умолчанию order_id — как настроено в кассе", secret=False
        ),
    )

    @staticmethod
    def _keys(credentials: dict[str, str]) -> tuple[str, str, str]:
        merchant = (credentials.get("merchant_id") or "").strip()
        key = (credentials.get("key") or "").strip()
        field = (credentials.get("account_field") or "").strip() or "order_id"
        if not merchant or not key:
            raise ProviderError("Payme: не заполнены ID кассы или ключ")
        return merchant, key, field

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        merchant, _key, field = self._keys(request.credentials)
        # Tiyin — a hundredth of a sum, which is exactly how amounts are
        # stored here, so nothing is converted.
        params = (
            f"m={merchant};ac.{field}={request.invoice_no};a={request.amount_minor};c={request.return_url}"
        )
        encoded = base64.b64encode(params.encode()).decode()
        return Checkout(url=f"{_CHECKOUT}/{encoded}")

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        call = _parse(raw_body)
        params = call.get("params") or {}

        # The first two methods name the order; the rest know only Payme's
        # own transaction id, which CreateTransaction stored for us.
        account = params.get("account") or {}
        for value in account.values():
            try:
                return PaymentRef(invoice_no=int(str(value)))
            except (TypeError, ValueError):
                continue

        remote_id = params.get("id")
        return PaymentRef(provider_payment_id=str(remote_id)) if remote_id else PaymentRef()

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
        _merchant, key, _field = self._keys(credentials)
        call = _parse(raw_body)
        request_id = call.get("id")
        params = call.get("params") or {}
        method = str(call.get("method") or "")
        notes = dict((meta or {}).get("payme") or {})

        if not _authorised(headers, key):
            raise PaymeRefusal(_fail(request_id, _ERR_AUTH, "user does not exist"), "Payme: неверная авторизация")

        if method == "CheckPerformTransaction":
            _require_amount(request_id, params, amount_minor)
            return _reply(_ok(request_id, {"allow": True}))

        if method == "CreateTransaction":
            return self._create(request_id, params, amount_minor, notes)

        if method == "PerformTransaction":
            return self._perform(request_id, params, notes)

        if method == "CancelTransaction":
            return self._cancel(request_id, params, notes)

        if method == "CheckTransaction":
            if str(params.get("id") or "") != str(notes.get("id") or ""):
                raise PaymeRefusal(
                    _fail(request_id, _ERR_TRANSACTION_NOT_FOUND), "Payme: транзакция не найдена"
                )
            return _reply(_ok(request_id, _state_of(notes)))

        if method == "GetStatement":
            # We answer per payment, so a statement over a period is not
            # something this endpoint can assemble. Payme accepts an empty
            # list; it reconciles against its own records anyway.
            return _reply(_ok(request_id, {"transactions": []}))

        raise PaymeRefusal(_fail(request_id, _ERR_CANNOT_PERFORM, method), f"Payme: метод {method!r} не поддержан")

    # ------------------------------------------------------------ methods

    def _create(self, request_id, params: dict, amount_minor: int, notes: dict) -> WebhookResult:
        remote_id = str(params.get("id") or "")
        known = str(notes.get("id") or "")

        if known and known != remote_id:
            # One order, one transaction: Payme must not open a second one
            # while the first is alive.
            raise PaymeRefusal(
                _fail(request_id, _ERR_CANNOT_PERFORM, "order already has a transaction"),
                "Payme: у заказа уже есть транзакция",
            )
        if known == remote_id and notes.get("state") is not None:
            if int(notes["state"]) != _STATE_CREATED:
                raise PaymeRefusal(
                    _fail(request_id, _ERR_CANNOT_PERFORM, "transaction is closed"),
                    "Payme: транзакция уже закрыта",
                )
            # A repeat of the same call gets the same answer, not a new one.
            return _reply(
                _ok(
                    request_id,
                    {
                        "create_time": int(notes["create_time"]),
                        "transaction": str(notes["transaction"]),
                        "state": _STATE_CREATED,
                    },
                )
            )

        _require_amount(request_id, params, amount_minor)

        started = params.get("time")
        try:
            stale = started is not None and _now_ms() - int(started) > _TRANSACTION_TTL_MS
        except (TypeError, ValueError):
            stale = False
        if stale:
            raise PaymeRefusal(
                _fail(request_id, _ERR_CANNOT_PERFORM, "transaction is too old"),
                "Payme: транзакция просрочена",
            )

        created = _now_ms()
        patch = {
            "id": remote_id,
            "transaction": remote_id,
            "create_time": created,
            "state": _STATE_CREATED,
        }
        return _reply(
            _ok(request_id, {"create_time": created, "transaction": remote_id, "state": _STATE_CREATED}),
            provider_payment_id=remote_id,
            patch=patch,
        )

    def _perform(self, request_id, params: dict, notes: dict) -> WebhookResult:
        remote_id = str(params.get("id") or "")
        if not notes or str(notes.get("id") or "") != remote_id:
            raise PaymeRefusal(_fail(request_id, _ERR_TRANSACTION_NOT_FOUND), "Payme: транзакция не найдена")

        state = int(notes.get("state") or 0)
        if state == _STATE_DONE:
            # Already performed — same numbers back, and no second delivery.
            return _reply(
                _ok(
                    request_id,
                    {
                        "transaction": str(notes["transaction"]),
                        "perform_time": int(notes["perform_time"]),
                        "state": _STATE_DONE,
                    },
                )
            )
        if state != _STATE_CREATED:
            raise PaymeRefusal(
                _fail(request_id, _ERR_CANNOT_PERFORM, "transaction is cancelled"),
                "Payme: транзакция отменена",
            )

        performed = _now_ms()
        return _reply(
            _ok(
                request_id,
                {"transaction": remote_id, "perform_time": performed, "state": _STATE_DONE},
            ),
            status=PaymentStatus.paid,
            provider_payment_id=remote_id,
            patch={**notes, "perform_time": performed, "state": _STATE_DONE},
        )

    def _cancel(self, request_id, params: dict, notes: dict) -> WebhookResult:
        remote_id = str(params.get("id") or "")
        if not notes or str(notes.get("id") or "") != remote_id:
            raise PaymeRefusal(_fail(request_id, _ERR_TRANSACTION_NOT_FOUND), "Payme: транзакция не найдена")

        was_done = int(notes.get("state") or 0) == _STATE_DONE
        state = _STATE_CANCELLED_AFTER_DONE if was_done else _STATE_CANCELLED
        cancelled = int(notes.get("cancel_time") or 0) or _now_ms()
        patch = {**notes, "state": state, "cancel_time": cancelled, "reason": params.get("reason")}

        return _reply(
            _ok(request_id, _state_of(patch)),
            # Cancelling a performed transaction is a refund; cancelling one
            # that never went through just closes it.
            status=PaymentStatus.refunded if was_done else PaymentStatus.failed,
            provider_payment_id=remote_id,
            patch=patch,
        )

    # ------------------------------------------------------------ refusals

    def error_body(self, *, form: dict[str, str], raw_body: bytes, found: bool) -> tuple[str, str]:
        """Payme answers 200 to everything; a refusal is a body, not a status."""
        request_id = _parse(raw_body).get("id")
        code = _ERR_ORDER_NOT_FOUND if not found else _ERR_CANNOT_PERFORM
        return _fail(request_id, code), "application/json"


# ---------------------------------------------------------------- helpers


def _reply(
    body: str,
    *,
    status: PaymentStatus = PaymentStatus.pending,
    provider_payment_id: str | None = None,
    patch: dict | None = None,
) -> WebhookResult:
    return WebhookResult(
        status=status,
        provider_payment_id=provider_payment_id,
        response_body=body,
        response_content_type="application/json",
        meta={"payme": patch} if patch else {},
    )


def _state_of(notes: dict) -> dict:
    return {
        "create_time": int(notes.get("create_time") or 0),
        "perform_time": int(notes.get("perform_time") or 0),
        "cancel_time": int(notes.get("cancel_time") or 0),
        "transaction": str(notes.get("transaction") or ""),
        "state": int(notes.get("state") or 0),
        "reason": notes.get("reason"),
    }


def _require_amount(request_id, params: dict, amount_minor: int) -> None:
    try:
        amount = int(params.get("amount"))
    except (TypeError, ValueError):
        amount = -1
    if amount != amount_minor:
        raise PaymeRefusal(_fail(request_id, _ERR_INVALID_AMOUNT), f"Payme: сумма не совпадает ({amount})")


def _authorised(headers: dict[str, str], key: str) -> bool:
    raw = (headers.get("authorization") or "").strip()
    scheme, _, encoded = raw.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return False
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    login, _, password = decoded.partition(":")
    return login == "Paycom" and password == key


def _parse(raw_body: bytes) -> dict:
    try:
        call = json.loads(raw_body or b"{}")
    except json.JSONDecodeError:
        return {}
    return call if isinstance(call, dict) else {}
