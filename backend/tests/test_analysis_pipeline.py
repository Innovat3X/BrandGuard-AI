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