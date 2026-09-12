"""A provider that isn't one — it just marks the payment paid.

For building and demoing a scenario end to end (payment block → delivery)
before any real merchant account exists, and for our own tests. It refuses
to run unless the bot is in test mode, so it can never quietly become the
way a live bot "takes money".
"""

from __future__ import annotations

from app.config import get_settings
from app.models.payment import PaymentStatus
from app.services.payments.base import Checkout, CheckoutRequest, PaymentRef, ProviderDefaults, ProviderError, WebhookResult


class TestProvider(ProviderDefaults):
    slug = "test"
    title = "Тестовая оплата (без денег)"
    hint = "Ничего не подключает: страница оплаты сразу отмечает заказ оплаченным. Нужна, чтобы проверить сценарий целиком — блок оплаты, выдачу после неё — до подключения настоящего провайдера."
    currencies = ("RUB", "KZT", "USD", "EUR")
    region = "manual"
    credential_fields = ()
    uses_callback = False
    has_test_mode = False

    async def create_checkout(self, request: CheckoutRequest) -> Checkout:
        if not request.is_test:
            raise ProviderError("Тестовая оплата доступна только в тестовом режиме")
        base = get_settings().public_base_url.rstrip("/")
        return Checkout(url=f"{base}/webhook/pay/test/{request.payment_id}")

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
        payment_id=None,
        provider_payment_id: str | None = None,
        meta: dict | None = None,
        currency: str = "",
    ) -> WebhookResult:
        return WebhookResult(status=PaymentStatus.paid, provider_payment_id=f"test-{invoice_no}")
