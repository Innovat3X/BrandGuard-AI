
from collections.abc import Sequence
from typing import Literal
from unicodedata import normalize
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


class StructuredClaim(BaseModel):
    """
    Internal representation of a claim extracted from submitted text.

    comparison_value must be a canonical value produced by a
    reliable extraction/mapping component. It is not a database field.
    """

    fact_key: str = Field(min_length=1)
    claimed_value: str = Field(min_length=1)
    comparison_value: str = Field(min_length=1)

    # Exact original content and offsets into that content.
    source_text: str = Field(min_length=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)

    severity: Severity

    @model_validator(mode="after")
    def validate_location(self):
        if not self.fact_key.strip():
            raise ValueError("fact_key cannot be blank.")

        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must exceed start_offset.")

        if self.end_offset > len(self.source_text):
            raise ValueError("Claim location exceeds the source text.")

        matched_text = self.source_text[
            self.start_offset:self.end_offset
        ]

        if matched_text != self.claimed_value:
            raise ValueError(
                "claimed_value must match the exact source-text range."
            )

        return self


class StructuredApprovedFact(BaseModel):
    """
    Internal input mapped from an applicable, approved fact version.

    This is not a new SQLAlchemy model or database schema.
    The caller must provide reliable structured values and must
    retrieve facts within the authenticated organisation's scope.
    """

    source_fact_version_id: UUID
    fact_key: str = Field(min_length=1)

    # Human-readable approved value and canonical comparison value.
    approved_value: str = Field(min_length=1)
    comparison_value: str = Field(min_length=1)

    fact_text: str = Field(min_length=1)
    source_url: str | None = None
    source_name: str = "Approved fact"
    status: Literal["approved"]

    @model_validator(mode="after")
    def validate_fact(self):
        if not self.fact_key.strip():
            raise ValueError("fact_key cannot be blank.")
        return self


def _normalise_key(value: str) -> str:
    """Normalise structured identifiers, not arbitrary fact semantics."""
    value = normalize("NFKC", value)
    return " ".join(value.casefold().split())


def _normalise_value(value: str) -> str:
    """
    Compare already-canonical values conservatively.

    This does not convert units, dates, currencies or equivalent
    natural-language statements into a shared meaning.
    """
    value = normalize("NFKC", value)
    return " ".join(value.casefold().split())


def _make_location(claim: StructuredClaim) -> TextRangeLocation:
    return TextRangeLocation(
        kind="text_range",
        start_offset=claim.start_offset,
        end_offset=claim.end_offset,
        matched_text=claim.claimed_value,
    )


def check_claims(
    claims: Sequence[StructuredClaim],
    approved_facts: Sequence[StructuredApprovedFact],
    *,
    fact_lookup_completed: bool,
) -> list[Finding]:
    """
    Compare structured claims against applicable approved facts.

    The fact lookup must be organisation-scoped and must select
    only approved, applicable versions before calling this function.

    A conflicting value is reported only when the upstream mapper
    supplies comparable canonical values for the same fact_key.
    """

    findings: list[Finding] = []

    for claim in claims:
        location = _make_location(claim)

        if not fact_lookup_completed:
            findings.append(
                Finding(
                    category=FindingCategory.FACTUAL_CLAIM,
                    severity=claim.severity,
                    result=FindingResult.CHECK_UNAVAILABLE,
                    explanation=(
                        "Approved-fact retrieval did not complete. "
                        "The claim could not be reliably checked."
                    ),
                    evidence=Evidence(
                        submitted_text=claim.claimed_value,
                        source_name="Approved-fact lookup",
                    ),
                    location=location,
                    detection_method=DetectionMethod.DETERMINISTIC,
                    requires_human_review=True,
                )
            )
            continue

        matching_facts = [
            fact
            for fact in approved_facts
            if _normalise_key(fact.fact_key)
            == _normalise_key(claim.fact_key)
        ]

        if not matching_facts:
            findings.append(
                Finding(
                    category=FindingCategory.FACTUAL_CLAIM,
                    severity=claim.severity,
                    result=FindingResult.UNSUPPORTED,
                    explanation=(
                        f"No applicable approved fact was found for "
                        f"the structured claim key '{claim.fact_key}'. "
                        "This does not prove that the claim is false."
                    ),
                    evidence=Evidence(
                        submitted_text=claim.claimed_value,
                        source_name="Approved-fact lookup",
                    ),
                    location=location,
                    detection_method=DetectionMethod.DETERMINISTIC,
                    requires_human_review=True,
                )
            )
            continue

        # Never choose an arbitrary source when multiple applicable
        # records match the same key. The retrieval layer should
        # normally provide one unambiguous applicable fact per key.
        if len(matching_facts) != 1:
            references = "; ".join(
                sorted({fact.fact_text for fact in matching_facts})
            )

            findings.append(
                Finding(
                    category=FindingCategory.FACTUAL_CLAIM,
                    severity=claim.severity,
                    result=FindingResult.INCONCLUSIVE,
                    explanation=(
                        f"Multiple approved fact records matched "
                        f"'{claim.fact_key}'. The applicable source "
                        "is ambiguous and requires verification."
                    ),
                    evidence=Evidence(
                        submitted_text=claim.claimed_value,
                        approved_reference=references,
                        source_name="Multiple approved fact records",
                    ),
                    location=location,
                    detection_method=DetectionMethod.DETERMINISTIC,
                    requires_human_review=True,
                )
            )
            continue

        fact = matching_facts[0]

        if _normalise_value(claim.comparison_value) == (
            _normalise_value(fact.comparison_value)
        ):
            # A supported match is not a governance finding.
            continue

        corrected_text = (
            claim.source_text[:claim.start_offset]
            + fact.approved_value
            + claim.source_text[claim.end_offset:]
        )

        findings.append(
            Finding(
                category=FindingCategory.FACTUAL_CLAIM,
                severity=claim.severity,
                result=FindingResult.CONFLICT,
                explanation=(
                    f"The submitted value '{claim.claimed_value}' "
                    f"differs from the approved value "
                    f"'{fact.approved_value}' for '{claim.fact_key}'. "
                    "This comparison assumes both values use the "
                    "same reliable canonical representation."
                ),
                evidence=Evidence(
                    submitted_text=claim.claimed_value,
                    approved_reference=fact.fact_text,
                    source_name=fact.source_name,
                    source_url=fact.source_url,
                ),
                source_fact_version_id=fact.source_fact_version_id,
                location=location,
                suggested_correction=corrected_text,
                detection_method=DetectionMethod.DETERMINISTIC,
                requires_human_review=True,
            )
        )

    return findings
