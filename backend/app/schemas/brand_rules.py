"""Request and response schemas for versioned brand rules."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


RuleCategory = Literal["tone", "terminology", "messaging", "other"]
RuleSeverity = Literal["info", "low", "medium", "high"]
RuleVersionStatus = Literal["draft", "approved", "archived"]


class _RuleTextFields(BaseModel):
    category: RuleCategory
    description: str | None = Field(default=None, max_length=2000)
    rule_text: str = Field(min_length=1, max_length=10000)
    severity: RuleSeverity = "medium"

    @field_validator("rule_text", mode="before")
    @classmethod
    def strip_rule_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class CreateBrandRuleRequest(_RuleTextFields):
    """Create a new brand rule with its first draft version."""

    title: str = Field(min_length=1, max_length=255)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class UpdateBrandRuleRequest(CreateBrandRuleRequest):
    """Replace the content of the latest draft version."""


class CreateBrandRuleVersionRequest(_RuleTextFields):
    """Append a new draft version without changing historical versions."""

    effective_from: datetime | None = None

    @field_validator("effective_from")
    @classmethod
    def require_timezone_aware_effective_from(cls, value):
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("effective_from must be timezone-aware.")
        return value


class BrandRuleVersionResponse(BaseModel):
    id: UUID
    version_number: int
    category: RuleCategory
    description: str | None
    rule_text: str
    severity: RuleSeverity
    status: RuleVersionStatus
    effective_from: datetime | None
    created_by: UUID
    approved_by: UUID | None
    approved_at: datetime | None
    created_at: datetime


class BrandRuleResponse(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    versions: list[BrandRuleVersionResponse]


class BrandRulesListResponse(BaseModel):
    items: list[BrandRuleResponse]
