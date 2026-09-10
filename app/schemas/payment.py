import uuid

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


class PublicationInfoOut(BaseModel):
    required: bool
    paid: bool
    # The first method's price, kept so an older frontend still renders.
    price_minor: int
    currency: str
    methods: list[PublicationMethodOut] = []


class PublicationCheckoutIn(BaseModel):
    """Which of the offered methods the client picked. Omitted means the
    first one, which is what a single-method deployment always wants."""

    provider: str | None = None
