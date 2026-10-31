"""Campaign schemas and active-window helpers."""
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def is_active(item, now=None):
    now = now or datetime.now(timezone.utc)
    return bool(item.active and (not item.starts_at or _utc(item.starts_at) <= now)
                and (not item.ends_at or now < _utc(item.ends_at)))


class Window(BaseModel):
    active: bool = False
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def valid_window(self):
        if self.starts_at and self.ends_at and _utc(self.ends_at) <= _utc(self.starts_at):
            raise ValueError("End time must be after start time")
        return self


class PromotionInput(Window):
    code: str = Field(min_length=1, max_length=32)
    discount_type: Literal["flat", "percent"]
    discount_value: float = Field(gt=0, allow_inf_nan=False)
    min_order: float = Field(default=0, ge=0, allow_inf_nan=False)
    max_discount: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    first_order_only: bool = False

    @field_validator("code")
    @classmethod
    def clean_code(cls, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]{1,32}", value):
            raise ValueError("Use letters, numbers, underscore or hyphen")
        return value

    @model_validator(mode="after")
    def valid_discount(self):
        if self.discount_type == "percent" and (self.discount_value > 100 or self.max_discount is None):
            raise ValueError("Percent offers require a cap and cannot exceed 100%")
        return self


class BannerInput(Window):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=300)
    image_url: str | None = Field(default=None, max_length=500)
    promo_code: str | None = Field(default=None, max_length=32)
    display_order: int = Field(default=0, ge=0, le=999)

    @field_validator("image_url")
    @classmethod
    def safe_image_url(cls, value):
        if value and not value.startswith("https://"):
            raise ValueError("Image URL must start with https://")
        return value or None

    @field_validator("promo_code")
    @classmethod
    def clean_code(cls, value):
        if not value:
            return None
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]{1,32}", value):
            raise ValueError("Invalid promo code")
        return value
