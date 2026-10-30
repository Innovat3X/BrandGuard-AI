"""Request and response schemas for versioned brand facts."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


FactKey = Literal[
    "product_price",
    "discount_percentage",
    "warranty_duration",
    "battery_life_duration",
    "product_weight",
    "product_capacity",
]

FactKind = Literal["currency", "percentage", "duration", "quantity"]

FACT_SPECS: dict[str, tuple[str, set[str]]] = {
    "product_price": ("currency", {"INR", "USD", "EUR", "GBP"}),
    "discount_percentage": ("percentage", {"%"}),
    "warranty_duration": ("duration", {"year", "years", "month", "months"}),
    "battery_life_duration": ("duration", {"hour", "hours", "day", "days"}),
    "product_weight": ("quantity", {"mg", "g", "kg", "lb"}),
    "product_capacity": ("quantity", {"ml", "l"}),
}


class StructuredFactValue(BaseModel):
    """Canonical, machine-comparable fact value."""

    kind: FactKind
    value: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=20)

    @field_validator("value", "unit", mode="before")
    @classmethod
    def strip_strings(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_value(self) -> "StructuredFactValue":
        try:
            number = Decimal(self.value)
        except (InvalidOperation, ValueError):
            raise ValueError("value must be a valid decimal string.") from None

        if not number.is_finite() or number < 0:
            raise ValueError("value must be a finite, non-negative number.")

        if self.kind == "currency":
            if self.unit not in {"INR", "USD", "EUR", "GBP"}:
                raise ValueError("Unsupported currency unit.")

        elif self.kind == "percentage":
            if self.unit != "%":
                raise ValueError("Percentage values must use '%' as unit.")

        elif self.kind == "duration":
            if self.unit not in {
                "year", "years", "month", "months",
                "hour", "hours", "day", "days",
            }:
                raise ValueError("Unsupported duration unit.")

        elif self.kind == "quantity":
            if self.unit not in {"mg", "g", "kg", "lb", "ml", "l"}:
                raise ValueError("Unsupported quantity unit.")

        return self


class CreateBrandFactRequest(BaseModel):
    """Create a draft fact; structured fields are optional for legacy facts."""

    label: str = Field(min_length=1, max_length=255)
    fact_text: str = Field(min_length=1)
    source_url: str | None = None
    fact_key: FactKey | None = None
    structured_value: StructuredFactValue | None = None

    @field_validator("label", "fact_text", mode="before")
    @classmethod
    def strip_required_strings(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_structured_pair(self) -> "CreateBrandFactRequest":
        if not self.label:
            raise ValueError("label must not be blank.")

        if not self.fact_text:
            raise ValueError("fact_text must not be blank.")

        if (self.fact_key is None) != (self.structured_value is None):
            raise ValueError(
                "fact_key and structured_value must be supplied together."
            )

        if self.fact_key is None or self.structured_value is None:
            return self

        expected_kind, allowed_units = FACT_SPECS[self.fact_key]
        structured = self.structured_value

        if structured.kind != expected_kind:
            raise ValueError(
                f"{self.fact_key} requires kind '{expected_kind}'."
            )

        if structured.unit not in allowed_units:
            raise ValueError(
                f"Unsupported unit for {self.fact_key}: {structured.unit}."
            )

        return self


class BrandFactVersionResponse(BaseModel):
    id: UUID
    version_number: int
    fact_text: str
    source_url: str | None
    fact_key: str | None
    structured_value: dict[str, Any] | None
    status: Literal["draft", "approved", "archived"]
    effective_from: datetime | None
    expires_at: datetime | None
    created_by: UUID
    approved_by: UUID | None
    approved_at: datetime | None
    created_at: datetime


class BrandFactResponse(BaseModel):
    id: UUID
    label: str
    created_at: datetime
    versions: list[BrandFactVersionResponse]


class BrandFactsListResponse(BaseModel):
    items: list[BrandFactResponse]