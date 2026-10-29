"""Conservative mapping of database knowledge into analysis inputs."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError

from app.analysis.claims import StructuredApprovedFact
from app.infrastructure.db.analysis_knowledge_loader import (
    ApprovedFactVersionRecord,
    ApprovedRuleVersionRecord,
)


RuleType = Literal[
    "forbidden_term",
    "required_term",
    "preferred_term",
]


@dataclass(frozen=True)
class MappedTerminologyRule:
    """Structured terminology rule accepted by the analysis checker."""

    source_rule_version_id: UUID
    rule_type: RuleType
    term: str
    severity: str
    status: Literal["approved"]
    replacement: str | None
    source_name: str
    case_sensitive: bool = False


_RULE_PATTERN = re.compile(
    r"^(forbidden_term|required_term|preferred_term)"
    r"(?:_case_sensitive)?\s*:\s*(.+)$"
)

# Approved key -> (required kind, supported units)
_STRUCTURED_FACT_SPECS: dict[str, tuple[str, frozenset[str]]] = {
    "product_price": (
        "currency",
        frozenset({"INR", "USD", "EUR", "GBP"}),
    ),
    "discount_percentage": (
        "percentage",
        frozenset({"%"}),
    ),
    "warranty_duration": (
        "duration",
        frozenset({"year", "years", "month", "months"}),
    ),
    "battery_life_duration": (
        "duration",
        frozenset({"hour", "hours", "day", "days"}),
    ),
    "product_weight": (
        "quantity",
        frozenset({"mg", "g", "kg", "lb"}),
    ),
    "product_capacity": (
        "quantity",
        frozenset({"ml", "l"}),
    ),
}

_CURRENCY_DISPLAY = {
    "INR": "₹",
    "USD": "US$",
    "EUR": "€",
    "GBP": "£",
}


def _parse_rule_text(
    rule_text: str,
) -> tuple[RuleType, str, str | None] | None:
    """Parse only the explicitly supported terminology syntax."""

    match = _RULE_PATTERN.fullmatch(rule_text.strip())

    if match is None:
        return None

    rule_type = match.group(1)
    payload = match.group(2).strip()

    if not payload or "\n" in payload or "\r" in payload:
        return None

    arrow_count = payload.count("->")

    if arrow_count > 1:
        return None

    if rule_type == "required_term":
        if arrow_count:
            return None

        return rule_type, payload, None

    if rule_type == "preferred_term" and arrow_count != 1:
        return None

    if arrow_count == 1:
        term, replacement = (
            part.strip() for part in payload.split("->", maxsplit=1)
        )

        if not term or not replacement:
            return None

        return rule_type, term, replacement

    if rule_type == "preferred_term":
        return None

    return rule_type, payload, None


def map_approved_terminology_rules(
    records: Sequence[ApprovedRuleVersionRecord],
) -> tuple[MappedTerminologyRule, ...] | None:
    """Map supported terminology rules or mark the check unavailable."""

    mapped: list[MappedTerminologyRule] = []

    for record in records:
        if record.category != "terminology":
            continue

        parsed = _parse_rule_text(record.rule_text)

        if parsed is None:
            return None

        rule_type, term, replacement = parsed

        rule_prefix = record.rule_text.strip().split(":", maxsplit=1)[0]
        case_sensitive = rule_prefix.endswith("_case_sensitive")

        mapped.append(
            MappedTerminologyRule(
                source_rule_version_id=record.version_id,
                rule_type=rule_type,
                term=term,
                severity=record.severity,
                status="approved",
                replacement=replacement,
                source_name=(
                    f"Approved terminology rule version "
                    f"{record.version_number}"
                ),
                case_sensitive=case_sensitive,
            )
        )

    return tuple(mapped)


def _normalise_decimal(raw_value: Any) -> str | None:
    """Return a canonical non-negative decimal string."""

    if not isinstance(raw_value, str) or not raw_value.strip():
        return None

    try:
        value = Decimal(raw_value.strip())
    except (InvalidOperation, ValueError):
        return None

    if not value.is_finite() or value < 0:
        return None

    rendered = format(value.normalize(), "f")

    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")

    return rendered or "0"


def _canonical_structured_value(
    *,
    fact_key: str,
    structured_value: dict[str, Any],
) -> tuple[str, str] | None:
    """Validate a fact's structured value and return display/comparison values."""

    spec = _STRUCTURED_FACT_SPECS.get(fact_key)

    if spec is None:
        return None

    expected_kind, allowed_units = spec

    kind = structured_value.get("kind")
    raw_value = structured_value.get("value")
    raw_unit = structured_value.get("unit")

    if not isinstance(kind, str) or kind != expected_kind:
        return None

    if not isinstance(raw_unit, str):
        return None

    unit = raw_unit.strip()

    if kind == "currency":
        unit = unit.upper()
    elif kind == "percentage":
        unit = "%"
    else:
        unit = unit.casefold()

    if unit not in allowed_units:
        return None

    number = _normalise_decimal(raw_value)

    if number is None:
        return None

    if kind == "currency":
        comparison_value = f"{unit} {number}"
        display_value = f"{_CURRENCY_DISPLAY[unit]}{number}"
        return display_value, comparison_value

    if kind == "percentage":
        return f"{number}%", f"{number} %"

    if kind == "duration":
        singular_units = {
            "years": "year",
            "months": "month",
            "hours": "hour",
            "days": "day",
        }
        plural_units = {
            "year": "years",
            "month": "months",
            "hour": "hours",
            "day": "days",
        }

        base_unit = singular_units.get(unit, unit)

        if number == "1":
            canonical_unit = base_unit
        else:
            canonical_unit = plural_units[base_unit]

        canonical_value = f"{number} {canonical_unit}"
        return canonical_value, canonical_value

    # Quantity values are compared without unit conversion.
    canonical_value = f"{number} {unit}"
    return canonical_value, canonical_value


def map_approved_facts(
    records: Sequence[ApprovedFactVersionRecord],
) -> tuple[StructuredApprovedFact, ...] | None:
    """Map explicitly structured approved facts into analysis inputs.

    Empty records mean retrieval completed and no approved facts exist.
    Any legacy free-text fact, incomplete structure or invalid value makes
    the whole mapping unavailable rather than silently ignoring evidence.
    """

    if not records:
        return ()

    mapped: list[StructuredApprovedFact] = []

    for record in records:
        # Legacy prose is retained in the database but is never interpreted
        # as a structured fact without an explicit structured representation.
        if record.fact_key is None or record.structured_value is None:
            return None

        if not isinstance(record.structured_value, dict):
            return None

        canonical = _canonical_structured_value(
            fact_key=record.fact_key,
            structured_value=record.structured_value,
        )

        if canonical is None:
            return None

        approved_value, comparison_value = canonical

        try:
            mapped_fact = StructuredApprovedFact(
                source_fact_version_id=record.version_id,
                fact_key=record.fact_key,
                approved_value=approved_value,
                comparison_value=comparison_value,
                fact_text=record.fact_text,
                source_url=record.source_url,
                source_name=(
                    f"Approved fact version {record.version_number}"
                ),
                status="approved",
            )
        except (ValidationError, ValueError, TypeError):
            return None

        mapped.append(mapped_fact)

    return tuple(mapped)