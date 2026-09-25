import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.payment import PaymentStatus


class PaymentSettingsIn(BaseModel):
    provider: str | None = None
    is_test: bool = True
    # Only the fields actually filled in are sent; a blank value means
    # "keep whatever is stored" (the API never returns saved secrets).
    credentials: dict[str, str] | None = None


class PaymentSettingsOut(BaseModel):
    provider: str | None
    is_test: bool
    filled_fields: list[str]
    callback_url: str | None
    #: Готова ли касса на самом деле принимать деньги. Отдельно от
    #: `provider`, потому что выбранный провайдер без ключей — это не
    #: подключённая касса, а конструктор показывал зелёное «Касса
    #: подключена» ровно по факту выбора. Владелец платил за публикацию и
    #: узнавал правду от первого покупателя, которому не открылась оплата.
    ready: bool = False
    #: Чего не хватает, человеческими названиями полей («shopId»,
    #: «Секретный ключ») — чтобы предупреждение могло сказать, что чинить.
    missing_fields: list[str] = []


class PaymentOut(BaseModel):
    id: uuid.UUID
    status: PaymentStatus
    amount_minor: int
    currency: str
    checkout_url: str | None = None


class PublicationMethodOut(BaseModel):
    """One way to pay for publishing, as offered at checkout."""

    provider: str
    title: str
    price_minor: int
    currency: str
    #: What one more period costs through this method; 0 if the launch is
    #: all this deployment charges.
    renewal_price_minor: int = 0


class PublicationInfoOut(BaseModel):
    required: bool
    paid: bool
    # The first method's price, kept so an older frontend still renders.
    price_minor: int
    currency: str
    methods: list[PublicationMethodOut] = []
    # What happens after the launch, so the paywall can say it before the
    # money is taken rather than in a message a month later.
    renewal_price_minor: int = 0
    renewal_period_days: int = 0
    renewal_grace_days: int = 0


class BillingStateOut(BaseModel):
    """Where a live bot stands with us — see `platform_billing.BillingState`."""

    state: str
    paid_until: datetime | None = None
    grace_until: datetime | None = None
    days_left: int | None = None
    price_minor: int = 0
    currency: str = ""
    period_days: int = 0


class PublicationCheckoutIn(BaseModel):
    """Which of the offered methods the client picked. Omitted means the
    first one, which is what a single-method deployment always wants."""

    provider: str | None = None
