from app.analysis.claims import (
    StructuredApprovedFact,
    StructuredClaim,
)
from app.analysis.pipeline import (
    aggregate_findings,
    build_analysis_response,
    run_analysis,
    run_terminology_slice,
)
from uuid import UUID

from app.analysis.contracts import (
    DetectionMethod,
    Evidence,
    Finding,
    FindingCategory,
    FindingResult,
    Severity,
)
from app.analysis.pipeline import (
    aggregate_findings,
    build_analysis_response,
    run_terminology_slice,
)
from app.analysis.terminology import ApprovedTerminologyRule


JOB_ID = UUID("11111111-1111-4111-8111-111111111111")
SUBMISSION_ID = UUID("22222222-2222-4222-8222-222222222222")
VERSION_ID = UUID("33333333-3333-4333-8333-333333333333")
RULE_VERSION_ID = UUID("44444444-4444-4444-8444-444444444444")


def make_rule():
    return ApprovedTerminologyRule(
        source_rule_version_id=RULE_VERSION_ID,
        rule_type="forbidden_term",
        term="cheap",
        replacement="affordable",
        severity=Severity.MEDIUM,
        status="approved",
    )


def make_finding():
    return Finding(
        category=FindingCategory.TERMINOLOGY,
        severity=Severity.MEDIUM,
        result=FindingResult.CONFLICT,
        explanation="An approved terminology rule was violated.",
        evidence=Evidence(
            submitted_text="cheap",
            approved_reference="affordable",
        ),
        source_rule_version_id=RULE_VERSION_ID,
        suggested_correction="affordable",
        detection_method=DetectionMethod.DETERMINISTIC,
        requires_human_review=True,
    )


def test_pipeline_returns_analysis_response():
    result = run_terminology_slice(
        job_id=JOB_ID,
        submission_id=SUBMISSION_ID,
        submission_version_id=VERSION_ID,
        content_text="Our product is cheap.",
        terminology_rules=[make_rule()],
    )

    assert result.status == "completed"
    assert result.job_id == JOB_ID
    assert result.submission_id == SUBMISSION_ID
    assert result.submission_version_id == VERSION_ID
    assert len(result.findings) == 1
    assert result.findings[0].result == FindingResult.CONFLICT
    assert result.summary.medium == 1
    assert result.summary.total == 1


def test_missing_terminology_rules_are_not_treated_as_passed():
    result = run_terminology_slice(
        job_id=JOB_ID,
        submission_id=SUBMISSION_ID,
        submission_version_id=VERSION_ID,
        content_text="Our product is excellent.",
        terminology_rules=[],
    )

    assert result.status == "partial"
    assert len(result.findings) == 1
    assert (
        result.findings[0].result
        == FindingResult.CHECK_UNAVAILABLE
    )


def test_aggregation_removes_duplicate_findings():
    first = make_finding()
    second = make_finding()

    results = aggregate_findings([first], [second])

    assert len(results) == 1


def test_aggregation_preserves_different_rule_versions():
    first = make_finding()

    second = first.model_copy(
        update={
            "source_rule_version_id": UUID(
                "55555555-5555-4555-8555-555555555555"
            )
        }
    )

    results = aggregate_findings([first, second])

    assert len(results) == 2


def test_summary_matches_aggregated_findings():
    finding = make_finding()

    response = build_analysis_response(
        job_id=JOB_ID,
        submission_id=SUBMISSION_ID,
        submission_version_id=VERSION_ID,
        findings=[finding, finding],
        status="completed",
    )

    assert len(response.findings) == 1
    assert response.summary.medium == 1
    assert response.summary.total == 1
    
FACT_VERSION_ID = UUID("66666666-6666-4666-8666-666666666666")


def make_price_claim(text: str) -> StructuredClaim:
    value = "₹1200"
    start = text.index(value)

    return StructuredClaim(
        fact_key="product_price",
        claimed_value=value,
        comparison_value="1200 INR",
        source_text=text,
        start_offset=start,
        end_offset=start + len(value),
        severity=Severity.HIGH,
    )


def make_price_fact() -> StructuredApprovedFact:
    return StructuredApprovedFact(
        source_fact_version_id=FACT_VERSION_ID,
        fact_key="product_price",
        approved_value="₹999",
        comparison_value="999 INR",
        fact_text="The approved product price is ₹999.",
        source_url="https://example.com/price",
        source_name="Approved pricing record",
        status="approved",
    )


def test_run_analysis_combines_terminology_and_claim_findings():
    text = "Our product is cheap at ₹1200."

    result = run_analysis(
        job_id=JOB_ID,
        submission_id=SUBMISSION_ID,
        submission_version_id=VERSION_ID,
        content_text=text,
        terminology_rules=[make_rule()],
        claims=[make_price_claim(text)],
        approved_facts=[make_price_fact()],
        fact_lookup_completed=True,
    )

    assert result.status == "completed"
    assert len(result.findings) == 2
    assert result.summary.medium == 1
    assert result.summary.high == 1
    assert result.summary.total == 2

    claim_finding = next(
        item for item in result.findings
        if item.category == FindingCategory.FACTUAL_CLAIM
    )
    assert claim_finding.result == FindingResult.CONFLICT
    assert claim_finding.source_fact_version_id == FACT_VERSION_ID


def test_run_analysis_marks_missing_rules_unavailable():
    result = run_analysis(
        job_id=JOB_ID,
        submission_id=SUBMISSION_ID,
        submission_version_id=VERSION_ID,
        content_text="Our product is excellent.",
        terminology_rules=None,
        claims=[],
        fact_lookup_completed=True,
    )

    assert result.status == "partial"
    assert any(
        item.result == FindingResult.CHECK_UNAVAILABLE
        and item.category == FindingCategory.TERMINOLOGY
        for item in result.findings
    )


def test_run_analysis_marks_missing_claim_extraction_unavailable():
    result = run_analysis(
        job_id=JOB_ID,
        submission_id=SUBMISSION_ID,
        submission_version_id=VERSION_ID,
        content_text="Our product is cheap.",
        terminology_rules=[make_rule()],
        claims=None,
    )

    assert result.status == "partial"
    assert any(
        item.result == FindingResult.CHECK_UNAVAILABLE
        and item.category == FindingCategory.FACTUAL_CLAIM
        for item in result.findings
    )


def test_run_analysis_marks_failed_fact_lookup_partial():
    text = "Our product is cheap at ₹1200."

    result = run_analysis(
        job_id=JOB_ID,
        submission_id=SUBMISSION_ID,
        submission_version_id=VERSION_ID,
        content_text=text,
        terminology_rules=[make_rule()],
        claims=[make_price_claim(text)],
        approved_facts=[],
        fact_lookup_completed=False,
    )

    assert result.status == "partial"
    assert any(
        item.result == FindingResult.CHECK_UNAVAILABLE
        and item.category == FindingCategory.FACTUAL_CLAIM
        for item in result.findings
    )
