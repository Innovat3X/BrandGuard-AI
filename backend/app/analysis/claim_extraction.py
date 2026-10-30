
"""Conservative deterministic extraction of numeric claims."""

import re
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation

from app.analysis.claims import StructuredClaim
from app.analysis.contracts import Severity


_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_CURRENCY = r"(?:INR|Rs\.?|₹|USD|US\$|EUR|€|GBP|£)"

_WEIGHT_ALIASES = {
    "mg": "mg",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
}

_CAPACITY_ALIASES = {
    "ml": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "l": "l",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
}

_WEIGHT_TO_GRAMS = {
    "mg": Decimal("0.001"),
    "g": Decimal("1"),
    "kg": Decimal("1000"),
    "lb": Decimal("453.59237"),
}

_CAPACITY_TO_MILLILITRES = {
    "ml": Decimal("1"),
    "l": Decimal("1000"),
}

_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "product_price",
        re.compile(
            rf"\b(?:price|cost|costs|priced\s+at|retails\s+for|sold\s+for)\b"
            rf"\s*(?:(?:is|of|at)\s*)?[:\-]?\s*"
            rf"(?P<value>(?:{_CURRENCY}\s*)?{_NUMBER}"
            rf"(?:\s*{_CURRENCY})?)",
            re.IGNORECASE,
        ),
        "currency",
    ),
    (
        "discount_percentage",
        re.compile(
            rf"\b(?:discount|save)\b"
            rf"\s*(?:(?:is|of|up\s+to)\s*)?[:\-]?\s*"
            rf"(?P<value>{_NUMBER}\s*%)",
            re.IGNORECASE,
        ),
        "percentage",
    ),
    (
        "warranty_duration",
        re.compile(
            rf"\b(?:warranty|warranted)\b"
            rf"\s*(?:(?:is|of|for|up\s+to)\s*)?[:\-]?\s*"
            rf"(?P<value>{_NUMBER}\s*(?:years?|yrs?|months?|mos?))\b",
            re.IGNORECASE,
        ),
        "duration",
    ),
    (
        "battery_life_duration",
        re.compile(
            rf"\b(?:battery\s+life|battery\s+lasts|runtime|run\s+time)\b"
            rf"\s*(?:(?:is|of|for|up\s+to)\s*)?[:\-]?\s*"
            rf"(?P<value>{_NUMBER}\s*(?:hours?|hrs?|days?))\b",
            re.IGNORECASE,
        ),
        "duration",
    ),
    (
        "product_weight",
        re.compile(
            rf"\b(?:weight|weighs?)\b"
            rf"\s*(?:(?:is|of|at)\s*)?[:\-]?\s*"
            rf"(?P<value>{_NUMBER}\s*"
            rf"(?:mg|g|kg|grams?|kilograms?|lbs?|pounds?))\b",
            re.IGNORECASE,
        ),
        "weight",
    ),
    (
        "product_capacity",
        re.compile(
            rf"\b(?:capacity|volume|holds?)\b"
            rf"\s*(?:(?:is|of|up\s+to)\s*)?[:\-]?\s*"
            rf"(?P<value>{_NUMBER}\s*"
            rf"(?:ml|millilit(?:er|re)s?|l|lit(?:er|re)s?))\b",
            re.IGNORECASE,
        ),
        "capacity",
    ),
)


def _number_string(raw: str) -> str | None:
    """Normalise numeric formatting without changing its value."""

    try:
        value = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None

    if not value.is_finite() or value < 0:
        return None

    rendered = format(value.normalize(), "f")

    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")

    return rendered or "0"


def _render_decimal(value: Decimal) -> str | None:
    """Render a finite, non-negative decimal without trailing zeroes."""

    if not value.is_finite() or value < 0:
        return None

    rendered = format(value.normalize(), "f")

    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")

    return rendered or "0"


def _canonical_value(value: str, kind: str) -> str | None:
    """Normalise supported values to conservative comparison formats."""

    text = value.strip()
    number_match = re.search(_NUMBER, text)

    if number_match is None:
        return None

    number = _number_string(number_match.group(0))

    if number is None:
        return None

    prefix = text[:number_match.start()].strip()
    suffix = text[number_match.end():].strip()

    if kind == "currency":
        marker = (prefix or suffix).casefold().replace(" ", "")

        currency_aliases = {
            "₹": "INR",
            "inr": "INR",
            "rs": "INR",
            "rs.": "INR",
            "us$": "USD",
            "usd": "USD",
            "€": "EUR",
            "eur": "EUR",
            "£": "GBP",
            "gbp": "GBP",
        }

        currency = currency_aliases.get(marker)

        # A price without an explicit currency is ambiguous.
        if currency is None:
            return None

        return f"{currency} {number}"

    unit = (suffix or prefix).strip().casefold()
    unit = re.sub(r"\s+", " ", unit)

    if kind == "percentage":
        return f"{number} %"

    if kind == "duration":
        unit_key = unit.rstrip(".")

        if unit_key in {"y", "yr", "yrs", "year", "years"}:
            unit_key = "year" if number == "1" else "years"
        elif unit_key in {"mo", "mos", "month", "months"}:
            unit_key = "month" if number == "1" else "months"
        elif unit_key in {"h", "hr", "hrs", "hour", "hours"}:
            unit_key = "hour" if number == "1" else "hours"
        elif unit_key in {"d", "day", "days"}:
            unit_key = "day" if number == "1" else "days"
        else:
            return None

        return f"{number} {unit_key}"

    if kind == "weight":
        unit_key = _WEIGHT_ALIASES.get(unit, "")
        factor = _WEIGHT_TO_GRAMS.get(unit_key)

        if factor is None:
            return None

        converted = _render_decimal(Decimal(number) * factor)

        if converted is None:
            return None

        return f"{converted} g"

    if kind == "capacity":
        unit_key = _CAPACITY_ALIASES.get(unit, "")
        factor = _CAPACITY_TO_MILLILITRES.get(unit_key)

        if factor is None:
            return None

        converted = _render_decimal(Decimal(number) * factor)

        if converted is None:
            return None

        return f"{converted} ml"

    return None


def extract_structured_claims(
    content_text: str,
) -> Sequence[StructuredClaim]:
    """Extract supported claims with offsets into the original text.

    Comparison values for supported weight claims are expressed in grams.
    Comparison values for supported capacity claims are expressed in
    millilitres. The original claim text and its offsets are preserved.

    An empty tuple means extraction succeeded but found no supported
    claims. An unavailable extractor is represented separately by None.
    """

    claims: list[StructuredClaim] = []
    occupied_spans: set[tuple[int, int]] = set()

    for fact_key, pattern, kind in _PATTERNS:
        for match in pattern.finditer(content_text):
            start, end = match.span("value")

            if (start, end) in occupied_spans:
                continue

            raw_value = match.group("value")
            comparison_value = _canonical_value(raw_value, kind)

            if comparison_value is None:
                continue

            claims.append(
                StructuredClaim(
                    fact_key=fact_key,
                    claimed_value=raw_value,
                    comparison_value=comparison_value,
                    source_text=content_text,
                    start_offset=start,
                    end_offset=end,
                    severity=Severity.MEDIUM,
                )
            )

            occupied_spans.add((start, end))

    claims.sort(
        key=lambda claim: (
            claim.start_offset,
            claim.end_offset,
            claim.fact_key,
        )
    )

    return tuple(claims)
