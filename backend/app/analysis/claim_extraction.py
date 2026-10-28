
"""Validate structured claim-extractor output before verification."""

import json
from collections.abc import Callable

from pydantic import ValidationError

from app.analysis.claims import StructuredClaim


ClaimPayloadProvider = Callable[[str], object]

_REQUIRED_FIELDS = {
    "fact_key",
    "claimed_value",
    "comparison_value",
    "start_offset",
    "end_offset",
    "severity",
}


def validate_claim_payload(
    content_text: str,
    payload: object,
) -> list[StructuredClaim] | None:
    """
    Validate claims returned by an extraction provider.

    Returns:
        A list, including an empty list, when extraction succeeded.
        None when the provider output is unavailable or malformed.
    """
    if not content_text.strip():
        return []

    if payload is None:
        return None

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None

    if not isinstance(payload, list):
        return None

    validated_claims: list[StructuredClaim] = []

    for item in payload:
        if not isinstance(item, dict):
            return None

        # Reject unexpected fields rather than trusting provider output.
        if set(item) != _REQUIRED_FIELDS:
            return None

        string_fields = (
            "fact_key",
            "claimed_value",
            "comparison_value",
            "severity",
        )

        if any(
            not isinstance(item[field], str)
            for field in string_fields
        ):
            return None

        start = item["start_offset"]
        end = item["end_offset"]

        # Python booleans are integer-like, so reject them explicitly.
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
        ):
            return None

        try:
            claim = StructuredClaim(
                fact_key=item["fact_key"],
                claimed_value=item["claimed_value"],
                comparison_value=item["comparison_value"],
                source_text=content_text,
                start_offset=start,
                end_offset=end,
                severity=item["severity"],
            )
        except (ValidationError, TypeError, ValueError):
            return None

        validated_claims.append(claim)

    return validated_claims


def build_claim_extractor(
    provider: ClaimPayloadProvider,
) -> Callable[[str], list[StructuredClaim] | None]:
    """
    Adapt a provider to the existing project's ClaimExtractor interface.

    Provider exceptions are allowed to propagate so the existing worker
    can apply its retry and failure-handling policy.
    """

    def extract(content_text: str) -> list[StructuredClaim] | None:
        if not content_text.strip():
            return []

        payload = provider(content_text)

        return validate_claim_payload(content_text, payload)

    return extract
