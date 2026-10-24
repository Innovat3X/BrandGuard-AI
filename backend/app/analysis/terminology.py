import re
from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.analysis.contracts import (
    DetectionMethod,
    Evidence,
    Finding,
    FindingCategory,
    FindingResult,
    Severity,
    TextRangeLocation,
)


class ApprovedTerminologyRule(BaseModel):
    """Internal input for an approved terminology rule."""

    source_rule_version_id: UUID
    rule_type: Literal[
        "forbidden_term",
        "required_term",
        "preferred_term",
    ]
    term: str = Field(min_length=1)
    severity: Severity
    status: Literal["approved"]
    replacement: str | None = None
    source_name: str = "Approved terminology rule"

    # Defaults to False to preserve existing checker behavior.
    case_sensitive: bool = False

    @model_validator(mode="after")
    def validate_rule(self):
        if not self.term.strip():
            raise ValueError("The terminology term cannot be blank.")

        if (
            self.rule_type == "preferred_term"
            and not (self.replacement or "").strip()
        ):
            raise ValueError(
                "A preferred-term rule requires a replacement."
            )

        if (
            self.replacement is not None
            and not self.replacement.strip()
        ):
            raise ValueError("A replacement cannot be blank.")

        return self


def find_term_occurrences(
    text: str,
    term: str,
    case_sensitive: bool = False,
) -> list[tuple[int, int]]:
    """Find exact word/phrase matches with zero-based offsets."""

    if not term or not term.strip():
        return []

    flags = 0 if case_sensitive else re.IGNORECASE

    pattern = re.compile(
        rf"(?<!\w){re.escape(term.strip())}(?!\w)",
        flags,
    )

    return [
        (match.start(), match.end())
        for match in pattern.finditer(text)
    ]


def check_terminology(
    text: str,
    rules: Sequence[ApprovedTerminologyRule],
) -> list[Finding]:
    """
    Apply explicitly configured, approved terminology rules.

    This function does not interpret arbitrary natural-language
    rule_text. Callers must supply structured rule information.

    Case-sensitive matching is opt-in so existing rules retain
    their previous behavior unless explicitly configured otherwise.
    """

    findings: list[Finding] = []

    for rule in rules:
        matches = find_term_occurrences(
            text,
            rule.term,
            case_sensitive=rule.case_sensitive,
        )

        if rule.rule_type == "required_term":
            if matches:
                continue

            explanation = (
                f"The required term '{rule.term}' was not "
                "found in the submitted content."
            )

            if rule.case_sensitive:
                explanation += (
                    " Matching is case-sensitive; the exact "
                    "approved spelling is required."
                )

            findings.append(
                Finding(
                    category=FindingCategory.TERMINOLOGY,
                    severity=rule.severity,
                    result=FindingResult.CONFLICT,
                    explanation=explanation,
                    evidence=Evidence(
                        approved_reference=rule.term,
                        source_name=rule.source_name,
                    ),
                    source_rule_version_id=rule.source_rule_version_id,
                    location=None,
                    suggested_correction=rule.term,
                    detection_method=DetectionMethod.DETERMINISTIC,
                    requires_human_review=True,
                )
            )
            continue

        for start, end in matches:
            matched_text = text[start:end]

            if rule.rule_type == "forbidden_term":
                explanation = (
                    f"The term '{matched_text}' conflicts with "
                    "an approved terminology rule."
                )
                correction = rule.replacement
            else:
                explanation = (
                    f"The preferred terminology is '{rule.replacement}', "
                    f"but '{matched_text}' appears in the submitted content."
                )
                correction = rule.replacement

            findings.append(
                Finding(
                    category=FindingCategory.TERMINOLOGY,
                    severity=rule.severity,
                    result=FindingResult.CONFLICT,
                    explanation=explanation,
                    evidence=Evidence(
                        submitted_text=matched_text,
                        approved_reference=correction,
                        source_name=rule.source_name,
                    ),
                    source_rule_version_id=rule.source_rule_version_id,
                    location=TextRangeLocation(
                        kind="text_range",
                        start_offset=start,
                        end_offset=end,
                        matched_text=matched_text,
                    ),
                    suggested_correction=correction,
                    detection_method=DetectionMethod.DETERMINISTIC,
                    requires_human_review=True,
                )
            )

    return findings