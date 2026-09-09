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


class PublicationInfoOut(BaseModel):
    required: bool
    paid: bool
    price_minor: int
    currency: str
