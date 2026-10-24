from uuid import uuid4

from app.analysis.claims import (
    StructuredApprovedFact,
    StructuredClaim,
    check_claims,
)
from app.analysis.contracts import (
    DetectionMethod,
    FindingCategory,
    FindingResult,
    Severity,
)
from app.analysis.pipeline import run_analysis
from app.analysis.terminology import (
    ApprovedTerminologyRule,
    check_terminology,
)


def test_terminology_finding_preserves_rule_and_evidence() -> None:
    text = "Our product is OldBrand."

    rule = ApprovedTerminologyRule(
        source_rule_version_id=uuid4(),
        rule_type="forbidden_term",
        term="OldBrand",
        severity=Severity.MEDIUM,
        status="approved",
        replacement="NewBrand",
    )

    findings = check_terminology(text, [rule])

    assert len(findings) == 1
    finding = findings[0]

    assert finding.category == FindingCategory.TERMINOLOGY
    assert finding.result == FindingResult.CONFLICT
    assert finding.source_rule_version_id == rule.source_rule_version_id
    assert finding.evidence.submitted_text == "OldBrand"
    assert finding.evidence.approved_reference == "NewBrand"
    assert finding.location is not None
    assert finding.location.matched_text == "OldBrand"


def test_claim_conflict_preserves_exact_fact_version_and_evidence() -> None:
    source_text = "The price is 10."
    start = source_text.index("10")
    end = start + len("10")
    fact_version_id = uuid4()

    claim = StructuredClaim(
        fact_key="price",
        claimed_value="10",
        comparison_value="10",
        source_text=source_text,
        start_offset=start,
        end_offset=end,
        severity=Severity.HIGH,
    )

    fact = StructuredApprovedFact(
        source_fact_version_id=fact_version_id,
        fact_key="price",
        approved_value="20",
        comparison_value="20",
        fact_text="The approved price is 20.",
        source_url="https://example.test/approved-price",
        source_name="Approved pricing source",
        status="approved",
    )

    findings = check_claims(
        [claim],
        [fact],
        fact_lookup_completed=True,
    )

    assert len(findings) == 1
    finding = findings[0]

    assert finding.result == FindingResult.CONFLICT
    assert finding.source_fact_version_id == fact_version_id
    assert finding.evidence.submitted_text == "10"
    assert finding.evidence.approved_reference == fact.fact_text
    assert finding.evidence.source_url == fact.source_url
    assert finding.location is not None
    assert finding.location.start_offset == start
    assert finding.location.end_offset == end
    assert finding.suggested_correction == "The price is 20."


def test_unavailable_fact_lookup_produces_partial_analysis() -> None:
    source_text = "The price is 10."
    start = source_text.index("10")

    claim = StructuredClaim(
        fact_key="price",
        claimed_value="10",
        comparison_value="10",
        source_text=source_text,
        start_offset=start,
        end_offset=start + 2,
        severity=Severity.MEDIUM,
    )

    rule = ApprovedTerminologyRule(
        source_rule_version_id=uuid4(),
        rule_type="forbidden_term",
        term="OldBrand",
        severity=Severity.MEDIUM,
        status="approved",
    )

    response = run_analysis(
        job_id=uuid4(),
        submission_id=uuid4(),
        submission_version_id=uuid4(),
        content_text=source_text,
        terminology_rules=[rule],
        claims=[claim],
        approved_facts=[],
        fact_lookup_completed=False,
    )

    assert response.status == "partial"

    unavailable = [
        finding
        for finding in response.findings
        if finding.result == FindingResult.CHECK_UNAVAILABLE
    ]

    assert len(unavailable) == 1
    assert unavailable[0].category == FindingCategory.FACTUAL_CLAIM
    assert unavailable[0].requires_human_review is True


def test_missing_approved_fact_is_unsupported_not_false() -> None:
    source_text = "The price is 10."
    start = source_text.index("10")

    claim = StructuredClaim(
        fact_key="price",
        claimed_value="10",
        comparison_value="10",
        source_text=source_text,
        start_offset=start,
        end_offset=start + 2,
        severity=Severity.MEDIUM,
    )

    findings = check_claims(
        [claim],
        [],
        fact_lookup_completed=True,
    )

    assert len(findings) == 1
    assert findings[0].result == FindingResult.UNSUPPORTED
    assert findings[0].source_fact_version_id is None
    assert "does not prove" in findings[0].explanation


def test_claim_from_different_text_is_marked_unavailable() -> None:
    content_text = "The current price is 10."
    stale_text = "The previous price was 15."
    start = stale_text.index("15")

    claim = StructuredClaim(
        fact_key="price",
        claimed_value="15",
        comparison_value="15",
        source_text=stale_text,
        start_offset=start,
        end_offset=start + 2,
        severity=Severity.HIGH,
    )

    rule = ApprovedTerminologyRule(
        source_rule_version_id=uuid4(),
        rule_type="forbidden_term",
        term="OldBrand",
        severity=Severity.MEDIUM,
        status="approved",
    )

    response = run_analysis(
        job_id=uuid4(),
        submission_id=uuid4(),
        submission_version_id=uuid4(),
        content_text=content_text,
        terminology_rules=[rule],
        claims=[claim],
        approved_facts=[],
        fact_lookup_completed=True,
    )

    assert response.status == "partial"

    assert any(
        finding.category == FindingCategory.FACTUAL_CLAIM
        and finding.result == FindingResult.CHECK_UNAVAILABLE
        for finding in response.findings
    )


def test_valid_claim_is_checked_when_another_claim_has_mismatched_text() -> None:
    content_text = "The current price is 10."
    current_start = content_text.index("10")

    current_claim = StructuredClaim(
        fact_key="price",
        claimed_value="10",
        comparison_value="10",
        source_text=content_text,
        start_offset=current_start,
        end_offset=current_start + 2,
        severity=Severity.HIGH,
    )

    stale_text = "The previous price was 15."
    stale_start = stale_text.index("15")

    stale_claim = StructuredClaim(
        fact_key="price",
        claimed_value="15",
        comparison_value="15",
        source_text=stale_text,
        start_offset=stale_start,
        end_offset=stale_start + 2,
        severity=Severity.HIGH,
    )

    fact_version_id = uuid4()
    approved_fact = StructuredApprovedFact(
        source_fact_version_id=fact_version_id,
        fact_key="price",
        approved_value="20",
        comparison_value="20",
        fact_text="The approved price is 20.",
        source_url=None,
        source_name="Approved pricing source",
        status="approved",
    )

    rule = ApprovedTerminologyRule(
        source_rule_version_id=uuid4(),
        rule_type="forbidden_term",
        term="OldBrand",
        severity=Severity.MEDIUM,
        status="approved",
    )

    response = run_analysis(
        job_id=uuid4(),
        submission_id=uuid4(),
        submission_version_id=uuid4(),
        content_text=content_text,
        terminology_rules=[rule],
        claims=[current_claim, stale_claim],
        approved_facts=[approved_fact],
        fact_lookup_completed=True,
    )

    assert response.status == "partial"

    # The valid claim must still be checked against its approved fact.
    assert any(
        finding.result == FindingResult.CONFLICT
        and finding.source_fact_version_id == fact_version_id
        for finding in response.findings
    )

    # The mismatched claim must be explicitly unavailable.
    assert any(
        finding.category == FindingCategory.FACTUAL_CLAIM
        and finding.result == FindingResult.CHECK_UNAVAILABLE
        for finding in response.findings
    )
