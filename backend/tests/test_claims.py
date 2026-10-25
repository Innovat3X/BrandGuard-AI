
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.analysis.claims import (
    StructuredApprovedFact,
    StructuredClaim,
    check_claims,
)
from app.analysis.contracts import FindingResult, Severity


FACT_VERSION_ID = UUID("66666666-6666-4666-8666-666666666666")


def make_claim(
    comparison_value: str = "1200 INR",
) -> StructuredClaim:
    text = "Our product costs ₹1200 today."

    return StructuredClaim(
        fact_key="product_price",
        claimed_value="₹1200",
        comparison_value=comparison_value,
        source_text=text,
        start_offset=18,
        end_offset=23,
        severity=Severity.HIGH,
    )


def make_fact(
    approved_value: str = "₹1200",
    comparison_value: str = "1200 INR",
) -> StructuredApprovedFact:
    return StructuredApprovedFact(
        source_fact_version_id=FACT_VERSION_ID,
        fact_key="product_price",
        approved_value=approved_value,
        comparison_value=comparison_value,
        fact_text=f"The approved product price is {approved_value}.",
        source_url="https://example.com/price",
        source_name="Approved pricing record",
        status="approved",
    )


def test_matching_claim_produces_no_finding():
    findings = check_claims(
        [make_claim()],
        [make_fact()],
        fact_lookup_completed=True,
    )

    assert findings == []


def test_conflicting_canonical_value_references_exact_fact_version():
    findings = check_claims(
        [make_claim("1200 INR")],
        [make_fact(approved_value="₹999", comparison_value="999 INR")],
        fact_lookup_completed=True,
    )

    assert len(findings) == 1

    finding = findings[0]
    assert finding.result == FindingResult.CONFLICT
    assert finding.source_fact_version_id == FACT_VERSION_ID
    assert finding.location.start_offset == 18
    assert finding.location.end_offset == 23
    assert finding.location.matched_text == "₹1200"
    assert finding.suggested_correction == (
        "Our product costs ₹999 today."
    )
    assert finding.evidence.source_url == "https://example.com/price"


def test_missing_approved_evidence_is_unsupported_not_false():
    findings = check_claims(
        [make_claim()],
        [],
        fact_lookup_completed=True,
    )

    assert len(findings) == 1
    assert findings[0].result == FindingResult.UNSUPPORTED
    assert "does not prove" in findings[0].explanation
    assert findings[0].source_fact_version_id is None


def test_failed_fact_lookup_is_unavailable():
    findings = check_claims(
        [make_claim()],
        [],
        fact_lookup_completed=False,
    )

    assert len(findings) == 1
    assert findings[0].result == FindingResult.CHECK_UNAVAILABLE


def test_multiple_matching_facts_are_inconclusive():
    first = make_fact()
    second = make_fact(
        approved_value="₹999",
        comparison_value="999 INR",
    ).model_copy(
        update={
            "source_fact_version_id": UUID(
                "77777777-7777-4777-8777-777777777777"
            )
        }
    )

    findings = check_claims(
        [make_claim()],
        [first, second],
        fact_lookup_completed=True,
    )

    assert len(findings) == 1
    assert findings[0].result == FindingResult.INCONCLUSIVE
    assert findings[0].source_fact_version_id is None


def test_claim_offsets_must_match_original_text():
    with pytest.raises(ValidationError):
        StructuredClaim(
            fact_key="product_price",
            claimed_value="₹1200",
            comparison_value="1200 INR",
            source_text="Our product costs ₹1200 today.",
            start_offset=17,
            end_offset=22,
            severity=Severity.HIGH,
        )
