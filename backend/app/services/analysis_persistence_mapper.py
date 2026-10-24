"""Map analysis findings to the database persistence contract.

The analysis response schema remains independent of database concerns.
This module derives a deterministic fingerprint at the integration
boundary without changing the shared Finding model.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from enum import Enum
from typing import Any
from uuid import UUID


PERSISTED_FINDING_FIELDS = frozenset(
    {
        "category",
        "severity",
        "result",
        "explanation",
        "evidence",
        "source_rule_version_id",
        "source_fact_version_id",
        "location",
        "suggested_correction",
        "detection_method",
        "requires_human_review",
        "finding_fingerprint",
    }
)

REQUIRED_FINDING_FIELDS = frozenset(
    {
        "category",
        "severity",
        "result",
        "explanation",
        "detection_method",
        "requires_human_review",
        "finding_fingerprint",
    }
)

ALLOWED_VALUES = {
    "category": frozenset(
        {
            "tone",
            "terminology",
            "messaging",
            "factual_claim",
            "visual",
            "accessibility",
            "other",
        }
    ),
    "severity": frozenset(
        {"info", "low", "medium", "high"}
    ),
    "result": frozenset(
        {
            "conflict",
            "unsupported",
            "inconclusive",
            "check_unavailable",
        }
    ),
    "detection_method": frozenset(
        {
            "deterministic",
            "ai_assisted",
            "ocr",
            "visual_check",
        }
    ),
}


class FindingMappingError(ValueError):
    """Raised when a finding cannot satisfy the persistence contract."""


def _model_or_mapping(value: Any) -> dict[str, Any]:
    """Convert a Pydantic model or mapping into a dictionary."""

    if hasattr(value, "model_dump") and callable(value.model_dump):
        result = value.model_dump(mode="python")

        if not isinstance(result, Mapping):
            raise FindingMappingError(
                "Finding model_dump() must return a mapping."
            )

        return dict(result)

    if isinstance(value, Mapping):
        return dict(value)

    raise FindingMappingError(
        "A finding must be a mapping or Pydantic-style model."
    )


def _storage_value(value: Any) -> Any:
    """Convert nested models and enums into database-ready values."""

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, UUID):
        return value

    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _storage_value(value.model_dump(mode="python"))

    if isinstance(value, Mapping):
        return {
            str(key): _storage_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_storage_value(item) for item in value]

    return value


def _fingerprint_value(value: Any) -> Any:
    """Produce canonical JSON-compatible values for hashing."""

    if isinstance(value, Enum):
        return _fingerprint_value(value.value)

    if isinstance(value, UUID):
        return str(value)

    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _fingerprint_value(value.model_dump(mode="python"))

    if isinstance(value, Mapping):
        return {
            str(key): _fingerprint_value(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }

    if isinstance(value, (list, tuple)):
        return [_fingerprint_value(item) for item in value]

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    raise FindingMappingError(
        "Unsupported value type in finding fingerprint: "
        f"{type(value).__name__}."
    )


def _fingerprint(payload: Mapping[str, Any]) -> str:
    """Compute a stable SHA-256 fingerprint."""

    canonical_json = json.dumps(
        _fingerprint_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    return hashlib.sha256(canonical_json).hexdigest()


def map_finding_for_persistence(
    finding: Any,
) -> dict[str, Any]:
    """Map one analysis finding into the repository's accepted format.

    The generated response ID and an existing fingerprint are excluded.
    The same semantic finding therefore receives the same fingerprint
    across retries.

    Rule/fact version identifiers and finding locations remain part
    of the fingerprint.
    """

    raw = _model_or_mapping(finding)

    # The response ID is not a database finding field.
    # Fingerprints must not depend on random response identifiers.
    raw.pop("id", None)
    raw.pop("finding_fingerprint", None)

    allowed_input_fields = (
        PERSISTED_FINDING_FIELDS - {"finding_fingerprint"}
    )

    unknown_fields = set(raw) - allowed_input_fields

    if unknown_fields:
        raise FindingMappingError(
            "Finding contains fields outside the persistence contract: "
            f"{sorted(unknown_fields)}"
        )

    payload = {
        key: _storage_value(value)
        for key, value in raw.items()
    }

    required_without_fingerprint = (
        REQUIRED_FINDING_FIELDS - {"finding_fingerprint"}
    )

    missing_fields = required_without_fingerprint - set(payload)

    if missing_fields:
        raise FindingMappingError(
            "Finding is missing required persistence fields: "
            f"{sorted(missing_fields)}"
        )

    for field, allowed_values in ALLOWED_VALUES.items():
        value = payload.get(field)

        if value not in allowed_values:
            raise FindingMappingError(
                f"Finding field '{field}' must be one of "
                f"{sorted(allowed_values)}; got {value!r}."
            )

    explanation = payload["explanation"]

    if (
        not isinstance(explanation, str)
        or not explanation.strip()
    ):
        raise FindingMappingError(
            "Finding explanation must be a non-empty string."
        )

    if not isinstance(payload["requires_human_review"], bool):
        raise FindingMappingError(
            "requires_human_review must be a boolean."
        )

    # Persist optional contract fields explicitly as null.
    for optional_field in (
        "evidence",
        "source_rule_version_id",
        "source_fact_version_id",
        "location",
        "suggested_correction",
    ):
        payload.setdefault(optional_field, None)

    payload["finding_fingerprint"] = _fingerprint(payload)

    return payload


def map_findings_for_persistence(
    findings: list[Any],
) -> list[dict[str, Any]]:
    """Map findings and remove duplicate logical findings."""

    mapped: list[dict[str, Any]] = []
    seen_fingerprints: set[str] = set()

    for finding in findings:
        item = map_finding_for_persistence(finding)
        fingerprint = item["finding_fingerprint"]

        if fingerprint in seen_fingerprints:
            continue

        seen_fingerprints.add(fingerprint)
        mapped.append(item)

    return mapped