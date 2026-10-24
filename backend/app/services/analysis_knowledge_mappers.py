"""Conservative mapping of database knowledge into analysis inputs.

Supported interim terminology syntax:
    forbidden_term: <term>
    forbidden_term: <term> -> <replacement>
    required_term: <term>
    required_term_case_sensitive: <term>
    preferred_term: <term> -> <replacement>

The optional '_case_sensitive' suffix can be used with any supported
rule type. This is an implementation convention, not a canonical
shared-contract change. Arbitrary prose is deliberately not parsed.

The database currently stores facts as free text. Those records cannot
safely become structured, comparable facts without additional fields.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

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


def _parse_rule_text(
    rule_text: str,
) -> tuple[RuleType, str, str | None] | None:
    """Parse only the explicit terminology syntax documented above."""

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
    """Map terminology rules or mark the whole check unavailable.

    Non-terminology rule categories are skipped.

    If any terminology rule uses unrecognised prose, return None
    instead of silently dropping it and analysing an incomplete set.
    An empty tuple means no terminology-category records were supplied.
    """

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


def map_approved_facts(
    records: Sequence[ApprovedFactVersionRecord],
) -> tuple[()] | None:
    """Map facts only when the set is empty.

    The current database fact model does not provide fact_key,
    approved_value, or comparison_value. Returning None for a non-empty
    set prevents free-text facts from being treated as structured
    evidence. The pipeline must report claim verification as unavailable.
    """

    if not records:
        return ()

    return None