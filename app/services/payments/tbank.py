"""Т-Банк (бывший Тинькофф) — интернет-эквайринг, Россия.

`Init` creates the payment and returns `PaymentURL`; `GetState` says where
it stands. Every request is signed with a `Token`:

    sha256( values of all top-level scalar params, plus Password,
            concatenated in order of their key names )

Nested objects (Receipt, DATA, Shops) are excluded from the signature.

The notification is *not* trusted on its own: like ЮKassa and PayMaster,
this adapter treats it as a nudge and re-reads `GetState`, so the money
question is answered by the bank's API rather than by a request body.

Сверено с официальной документацией банка (docs/tbank-docs.md, 5 октября 2026): тестовый хост,
подпись `Token` и нотификации, `Confirm` для двухстадийных терминалов, `Init` для автоплатежей, коды
ошибок. Ничего из этого не проверено на живом терминале — см. docs/live-payment-tests.md.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import ssl
import uuid

import certifi
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
    Receipt,
    RecurringMode,
    RecurringSetup,
    WebhookResult,
    kop,
    receipt_from_credentials,
)

logger = logging.getLogger(__name__)

_BASE = "https://securepay.tinkoff.ru/v2"
_BASE_TEST = "https://rest-api-test.tinkoff.ru/v2"

#: Fields that are objects, not values — excluded from the token.
_UNSIGNED = {"Token", "Receipt", "DATA", "Shops", "Items"}

#: Only CONFIRMED, deliberately. On a two-stage terminal AUTHORIZED means the
#: money is held, not taken — handing over goods for a hold would be giving
#: them away to anyone who can cancel the authorisation.
_PAID = {"CONFIRMED"}
# REVERSED — отмена холда (деньги не списывались), поэтому это не возврат, а неуспех.
_FAILED = {"REJECTED", "CANCELED", "DEADLINE_EXPIRED", "AUTH_FAIL", "REVERSED", "PARTIAL_REVERSED"}
_REFUNDED = {"REFUNDED", "PARTIAL_REFUNDED"}


def receipt_tbank(r: Receipt) -> dict:
    """Суммы в копейках, Amount = Price * Quantity. Ставки vat20/vat120 больше
    не принимаются — только vat22/vat122."""
    out: dict = {
        "Taxation": r.tax_system.value,
        "Items": [
            {
                "Name": i.name,
                "Price": kop(i.price),
                "Quantity": float(i.qty),
                "Amount": kop(i.total),
                "Tax": i.vat.value,
                "PaymentMethod": i.method.value,
                "PaymentObject": i.obj.value,
            }
            for i in r.items
        ],
    }
    if r.email:
        out["Email"] = r.email
    if r.phone:
        out["Phone"] = r.phone
    return out  # Receipt НЕ участвует в Token


def _receipt(credentials: dict[str, str], description: str, amount_minor: int, buyer: tuple = (None, None)) -> dict:
    """`Receipt` для Init. Пусто, если продавец не указал почту для чеков —
    тогда платёж идёт как раньше."""
    receipt = receipt_from_credentials(
        credentials, _clean(description), amount_minor, tax_key="taxation", vat_key="tax",
        buyer_email=buyer[0], buyer_phone=buyer[1],
    )
    return {"Receipt": receipt_tbank(receipt)} if receipt else {}


#: Символы, которые банк экранирует или отвергает в строках (документация, «Правила работы»).
_UNSAFE = re.compile(r"[\'\"&<>]")


def _clean(text: str) -> str:
    """Название бота вроде «Бот "Магазин" & Co» ломает запрос или подпись — вычищаем."""
    return re.sub(r"\s+", " ", _UNSAFE.sub(" ", text or "")).strip()


def _base(terminal_key: str, is_test: bool) -> str:
    """Тестовый режим — тот же терминал и пароль, но хост `rest-api-test`. Исключение: терминал с
    приставкой DEMO (для тест-кейсов из ЛК) живёт на боевом хосте — туда и шлём."""
    if is_test and not terminal_key.upper().endswith("DEMO"):
        return _BASE_TEST
    return _BASE


def _http_client() -> httpx.AsyncClient:
    """Банк переходит на сертификаты Минцифры, которых нет в certifi: если задан файл с ними
    (TBANK_CA_BUNDLE), добавляем его к обычному хранилищу. Проверку не отключаем."""
    bundle = (get_settings().tbank_ca_bundle or "").strip()
    verify: ssl.SSLContext | bool = True
    if bundle:
        if os.path.isfile(bundle):
            context = ssl.create_default_context(cafile=certifi.where())
            context.load_verify_locations(cafile=bundle)
            verify = context
        else:
            logger.warning("Т-Банк: TBANK_CA_BUNDLE=%s не найден — используется обычное хранилище", bundle)
    return httpx.AsyncClient(timeout=30, verify=verify)


#: Коды ошибок, которые продавцу нужно объяснить по-человечески (справочник банка, docs/tbank-docs.md §21).
_HINTS = {
    "10": "платежи по сохранённым реквизитам не включены на терминале — попроси персонального менеджера "
    "Т-Банка включить автоплатежи",
    "20": "такой номер заказа уже использован",
    "204": "неверный Terminal Key или пароль терминала",
    "205": "терминал не найден — проверь Terminal Key",
    "322": "неверный Terminal Key или пароль терминала",
    "202": "терминал заблокирован — обратись в поддержку банка",
    "648": "магазин заблокирован или не активирован — обратись в поддержку банка",
    "253": "валюта не разрешена для терминала (принимаются только рубли)",
    "254": "дополнительные возможности отключены — включает менеджер банка",
    "308": "ошибка чека: сумма позиций не равна сумме платежа",
    "309": "терминалу нужен чек: включи «Передавать чек» и заполни почту, ставку и систему налогообложения",
    "323": "ошибка чека: суммы в чеке и платеже не совпадают",
    "334": "ошибка чека: суммы в чеке и платеже не совпадают",
    "329": "в чеке нужны почта или телефон",
    "1125": "неверный тип операции автоплатежа (OperationInitiatorType)",
    "1126": "тип операции автоплатежа не согласован с сохранённой картой",
    "1235": "для карт «Мир» нужно настроить подтверждение 3DS 2.0 — напиши в поддержку банка",
    "103": "недостаточно средств на карте",
    "116": "недостаточно средств на карте",
    "1051": "недостаточно средств на карте",
    "252": "истёк срок действия карты",
    "1033": "истёк срок действия карты",
    "1054": "истёк срок действия карты",
    "1057": "владелец карты запретил такие списания",
    "1058": "владелец карты запретил такие списания",
    "1041": "карта утеряна",
    "262": "истёк срок родительского платежа — карту нужно привязать заново",
    "107": "сохранённая карта не найдена — карту нужно привязать заново",
    "104": "ошибка выполнения регулярного списания",
}


class _Unknown(ProviderError):
    """Результат вызова неизвестен: ответ 5xx или обрыв связи. Банк мог выполнить операцию —
    повторять её вслепую нельзя, сначала смотрим состояние платежа (`GetState`)."""


def _as_text(value) -> str:
    """Булевы в подписи — строки `true`/`false` (как в документации Т-Банка), а не `True`."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _token(payload: dict, password: str) -> str:
    values = {key: value for key, value in payload.items() if key not in _UNSIGNED}
    # Вложенное в подпись не входит, а null «не учитывается» (документация, проверка Token уведомления).
    values = {key: value for key, value in values.items() if value is not None and not isinstance(value, (dict, list))}
    values["Password"] = password
    joined = "".join(_as_text(values[key]) for key in sorted(values))
    return hashlib.sha256(joined.encode()).hexdigest()


class TBankProvider(ProviderDefaults):
    slug = "tbank"
    title = "Т-Банк (Тинькофф)"
    hint = (
        "Terminal Key и пароль — в личном кабинете, «Магазины → Терминалы». В настройках терминала выбери "
        "тип «Универсальное» и включи «Готовую платёжную форму» с нужными способами оплаты — без этого банк не "
        "вернёт ссылку на оплату. Если подключена онлайн-касса, включи ниже «Передавать чек». Подписки "
        "работают, только если менеджер банка включил платежи по сохранённым реквизитам. Адрес уведомлений мы "
        "передаём в каждом платеже сами."
    )
    currencies = ("RUB",)
    region = "ru"
    supports_status_check = True
    #: Адрес уведомлений уходит в каждом платеже сам — вписывать его в кабинете не нужно.
    sends_own_callback_url = True
    # Автоплатёж: Init с Recurrent="Y" и CustomerKey, банк возвращает RebillId
    # в нотификации, дальше Init нового платежа + Charge(PaymentId, RebillId).
    # Поля сверены с типизированной реализацией github.com/nikita-vanyasin/tinkoff
    # (InitRequest.Recurrent "Y", InitRequest.CustomerKey, Notification.RebillId,
    # ChargeRequest.PaymentId/.RebillId) — не по памяти.
    recurring = RecurringMode.token
    credential_fields = (
        CredentialField("terminal_key", "Terminal Key", "идентификатор терминала", secret=False),
        CredentialField("password", "Пароль терминала", "он же Secret Key"),
        # Чек 54-ФЗ: обязателен, если к терминалу подключена онлайн-касса. Покупатель из
        # Telegram почту не оставляет, поэтому чек уходит на адрес продавца.
        CredentialField(
            "fiscalization_enabled", "Передавать чек (54-ФЗ)", "1 — да, 0 или пусто — нет. Включай, только если у кассы подключена онлайн-касса",
            secret=False, required=False,
        ),
        CredentialField("fiscal_email", "Почта для чеков (если есть онлайн-касса)", "email для Receipt", secret=False, required=False),
        CredentialField(
            "taxation", "Система налогообложения", "osn, usn_income (по умолчанию), usn_income_outcome, esn или patent",
            secret=False, required=False),
        CredentialField("tax", "Ставка НДС в чеке", "none (по умолчанию), vat0, vat5, vat7, vat10, vat22; vat20 больше не принимается", secret=False, required=False),
    )

    @staticmethod
    def _keys(credentials: dict[str, str]) -> tuple[str, str]:
        terminal = (credentials.get("terminal_key") or "").strip()
        password = (credentials.get("password") or "").strip()
        if not terminal or not password:
            raise ProviderError("Т-Банк: не заполнены Terminal Key или пароль терминала")
        return terminal, password

    async def _call(self, method: str, payload: dict, credentials: dict[str, str], *, is_test: bool = False) -> dict:
        terminal, password = self._keys(credentials)
        body = {"TerminalKey": terminal, **payload}
        body["Token"] = _token(body, password)

        try:
            async with _http_client() as client:
                response = await client.post(f"{_base(terminal, is_test)}/{method}", json=body)
        except httpx.HTTPError as exc:
            raise _Unknown(f"Т-Банк: нет ответа ({type(exc).__name__})") from exc
        if response.status_code >= 500:
            raise _Unknown(f"Т-Банк: HTTP {response.status_code}")
        if response.status_code >= 400:
            raise ProviderError(f"Т-Банк: HTTP {response.status_code}")
        try:
            parsed = response.json()
        except ValueError as exc:
            raise ProviderError("Т-Банк: непонятный ответ") from exc
        # Успех — это `Success` И нулевой код ошибки; отказ приходит с HTTP 200 и `Success: false`.
        code = str(parsed.get("ErrorCode") or "0")
        if not parsed.get("Success") or code != "0":
            detail = _HINTS.get(code) or parsed.get("Message") or parsed.get("Details") or "отказ"
            raise ProviderError(f"Т-Банк: {detail}" + (f" (код {code})" if code != "0" else ""))
        return parsed

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        base = get_settings().public_base_url.rstrip("/")
        receipt = _receipt(
            request.credentials, request.description, request.amount_minor, (request.buyer_email, request.buyer_phone)
        )
        customer_key = str(request.telegram_user_id or request.payment_id)[:36]
        subscription = bool(request.extra.get("subscription"))
        payload = {
            # Kopecks, which is what we store anyway.
            "Amount": request.amount_minor,
            # Только буквы и цифры: в реестре банка номер заказа без спецсимволов, а UUID с дефисами — лишнее.
            "OrderId": request.payment_id.hex,
            # `PayType` не передаём: он не должен противоречить настройке терминала продавца, а у
            # двухстадийного терминала платёж остаётся AUTHORIZED — его списывает `_read` через Confirm.
            **receipt,
            "Description": _clean(request.description or "Оплата")[:140],
            "SuccessURL": request.return_url,
            "FailURL": request.return_url,
            "NotificationURL": f"{base}/webhook/pay/tbank",
            **(
                {
                    "Recurrent": "Y",
                    # Банк привязывает RebillId к этому ключу, поэтому он — покупатель, а не заказ.
                    # Не длиннее 36 знаков.
                    "CustomerKey": customer_key,
                    # Родительский платёж подписки (CC-покупка): тип операции лежит в DATA, а DATA в
                    # подпись не входит.
                    "DATA": {"OperationInitiatorType": "1"},
                }
                if subscription
                else {}
            ),
        }
        parsed = await self._call("Init", payload, request.credentials, is_test=request.is_test)
        url = parsed.get("PaymentURL")
        if not url:
            raise ProviderError(
                "Т-Банк: банк не вернул ссылку на оплату — у терминала не включена платёжная форма. "
                "В кабинете: Магазины → Терминалы → Настроить → «Универсальное», затем «Приём оплаты» → "
                "«Готовая платёжная форма»."
            )
        payment_id = parsed.get("PaymentId")
        # Запоминаем, на каком хосте создан платёж и какой чек отправлен: уведомление и «Я оплатил» идут
        # без настроек платежа, а `Confirm` двухстадийного терминала требует тот же чек.
        notes: dict = {"tbank_test": bool(request.is_test)}
        if receipt:
            notes["tbank_receipt"] = receipt["Receipt"]
        if subscription:
            notes["tbank_customer_key"] = customer_key
        return Checkout(
            url=url, provider_payment_id=str(payment_id) if payment_id is not None else None, meta=notes
        )

    def locate_payment(self, *, headers: dict[str, str], raw_body: bytes, form: dict[str, str]) -> PaymentRef:
        try:
            event = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            event = {}
        raw_order = str(event.get("OrderId") or form.get("OrderId") or "")
        try:
            # И `hex` (как создаём сейчас), и UUID с дефисами (платежи, созданные раньше).
            return PaymentRef(payment_id=uuid.UUID(raw_order))
        except ValueError:
            remote = event.get("PaymentId") or form.get("PaymentId")
            return PaymentRef(provider_payment_id=str(remote) if remote else None)

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
        payload = event if isinstance(event, dict) and event else dict(form)

        # Сначала подпись (документация: проверять `Token` до любых действий): чужой запрос не должен
        # заставлять нас ходить в банк с ключами продавца. Сумму и статус всё равно берём у банка.
        _terminal, password = self._keys(credentials)
        given = str(payload.get("Token") or "").strip().lower()
        if not given or not hmac.compare_digest(_token(payload, password), given):
            raise ProviderError("Т-Банк: подпись уведомления не совпала")

        remote_id = provider_payment_id or payload.get("PaymentId")
        if not remote_id:
            raise ProviderError("Т-Банк: уведомление без PaymentId")
        result = await self._read(credentials, str(remote_id), amount_minor, payment_id, meta)
        notes = dict(result.meta or {})
        rebill = payload.get("RebillId")
        if rebill:
            notes["tbank_rebill_id"] = str(rebill)
        customer = payload.get("CustomerKey")
        if customer:
            notes["tbank_customer_key"] = str(customer)
        # Банк повторяет уведомление (раз в час сутки, потом раз в день), пока не увидит ровно «OK».
        return WebhookResult(
            status=result.status,
            provider_payment_id=result.provider_payment_id,
            response_body="OK",
            meta=notes,
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
            raise ProviderError("Т-Банк: платёж ещё не создан")
        return await self._read(credentials, provider_payment_id, amount_minor, payment_id, meta)

    def recurring_setup(self, settled: dict) -> RecurringSetup | None:
        rebill = (settled or {}).get("tbank_rebill_id")
        if not rebill:
            return None
        return RecurringSetup(token=str(rebill), customer=str((settled or {}).get("tbank_customer_key") or ""))

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
        #: The short numeric invoice number of *this* charge. Robokassa signs
        #: the recurring call with it; the others never look at it.
        invoice_no: int | None = None,
    ) -> WebhookResult:
        """Две операции, потому что Charge проводит уже созданный платёж.

        `Init` заводит платёж на этот период — без `Recurrent`, договорённость уже есть, — с типом
        операции «R» (регулярное списание магазином) и чеком: чек в `Charge` не передаётся, он берётся
        из `Init`. `Charge` списывает по сохранённому RebillId без участия покупателя.
        """
        description = _clean(description or "Продление подписки")
        receipt = _receipt(
            credentials,
            description,
            amount_minor,
            (credentials.get("_buyer_email"), credentials.get("_buyer_phone")),  # кладёт subscription_service
        )
        started = await self._call(
            "Init",
            {
                "Amount": amount_minor,
                "OrderId": payment_id.hex,
                **receipt,
                "Description": description[:140],
                **({"CustomerKey": setup.customer[:36]} if setup.customer else {}),
                "DATA": {"OperationInitiatorType": "R"},
            },
            credentials,
            is_test=is_test,
        )
        remote_id = started.get("PaymentId")
        if remote_id is None:
            raise ProviderError("Т-Банк: Init не вернул PaymentId")
        remote_id = str(remote_id)
        notes = {"tbank_test": bool(is_test), **({"tbank_receipt": receipt["Receipt"]} if receipt else {})}

        try:
            charged = await self._call(
                "Charge", {"PaymentId": remote_id, "RebillId": setup.token}, credentials, is_test=is_test
            )
        except _Unknown:
            # Банк мог списать деньги, а ответ потерялся. Повторять Charge вслепую нельзя (идемпотентность
            # на странице метода не описана) — узнаём состояние платежа.
            logger.warning("Т-Банк: Charge %s без ответа, смотрим GetState", remote_id)
            return await self._read(credentials, remote_id, amount_minor, payment_id, notes)

        status = str(charged.get("Status") or "").upper()
        if status in _PAID:
            amount = charged.get("Amount")
            if amount is not None and int(amount) != amount_minor:
                raise ProviderError(f"Т-Банк: списано {amount} вместо {amount_minor}")
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=remote_id)
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=remote_id)
        # AUTHORIZED у двухстадийного терминала — деньги заблокированы, а не списаны; `_read` подтверждает
        # списание (Confirm) и перечитывает платёж.
        return await self._read(credentials, remote_id, amount_minor, payment_id, notes)

    @staticmethod
    def _check_order(parsed: dict, payment_id: uuid.UUID | None) -> None:
        """Платёж в банке должен быть именно по нашему заказу (банк советует сверять OrderId)."""
        raw = str(parsed.get("OrderId") or "").strip()
        if not raw or payment_id is None:
            return
        try:
            theirs = uuid.UUID(raw)
        except ValueError:
            return
        if theirs != payment_id:
            raise ProviderError("Т-Банк: платёж относится к другому заказу")

    async def _read(
        self,
        credentials: dict[str, str],
        remote_id: str,
        amount_minor: int,
        payment_id: uuid.UUID | None = None,
        meta: dict | None = None,
    ) -> WebhookResult:
        test = bool((meta or {}).get("tbank_test"))
        parsed = await self._call("GetState", {"PaymentId": remote_id}, credentials, is_test=test)
        self._check_order(parsed, payment_id)
        status = str(parsed.get("Status") or "").upper()

        if status == "AUTHORIZED":
            # Двухстадийный терминал: деньги только заблокированы. Товар выдаёт бот сразу, так что
            # списываем (Confirm) и верим только следующему чтению — холд сам не вечен.
            receipt = (meta or {}).get("tbank_receipt")
            try:
                await self._call(
                    "Confirm",
                    {"PaymentId": remote_id, **({"Receipt": receipt} if receipt else {})},
                    credentials,
                    is_test=test,
                )
            except ProviderError as exc:
                # Не вышло сейчас — банк повторит уведомление, а покупатель может нажать «Я оплатил».
                logger.warning("Т-Банк: Confirm %s не прошёл: %s", remote_id, exc)
                return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(remote_id))
            parsed = await self._call("GetState", {"PaymentId": remote_id}, credentials, is_test=test)
            status = str(parsed.get("Status") or "").upper()

        notes: dict = {}
        # `RebillId` приходит и в нотификации, и (необязательно) в ответе GetState — берём, где есть.
        if parsed.get("RebillId"):
            notes["tbank_rebill_id"] = str(parsed["RebillId"])

        if status in _PAID:
            amount = parsed.get("Amount")
            # GetState reports kopecks, the same unit we asked to charge.
            # Нет суммы в ответе банка — сверить нечего, а значит и платить «оплачено» нельзя.
            try:
                same = amount is not None and int(amount) == amount_minor
            except (TypeError, ValueError):
                same = False
            if not same:
                raise ProviderError(f"Т-Банк: сумма не совпадает (в банке {amount})")
            return WebhookResult(status=PaymentStatus.paid, provider_payment_id=str(remote_id), meta=notes)
        if status in _REFUNDED:
            return WebhookResult(status=PaymentStatus.refunded, provider_payment_id=str(remote_id), meta=notes)
        if status in _FAILED:
            return WebhookResult(status=PaymentStatus.failed, provider_payment_id=str(remote_id), meta=notes)
        return WebhookResult(status=PaymentStatus.pending, provider_payment_id=str(remote_id), meta=notes)
