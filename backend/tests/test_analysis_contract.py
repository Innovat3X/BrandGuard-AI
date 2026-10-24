from uuid import uuid4

from app.analysis.contracts import (
    AnalysisResponse,
    DetectionMethod,
    Evidence,
    Finding,
    FindingCategory,
    FindingResult,
    ImageBoundingBoxLocation,
    Severity,
    TextRangeLocation,
    build_summary,
)


def test_finding_contains_required_contract_fields():
    rule_version_id = uuid4()

    finding = Finding(
        category=FindingCategory.TERMINOLOGY,
        severity=Severity.MEDIUM,
        result=FindingResult.CONFLICT,
        explanation="The text uses a term that conflicts with an approved rule.",
        evidence=Evidence(
            submitted_text="cheap",
            approved_reference="affordable",
            source_name="Approved terminology rule",
        ),
        source_rule_version_id=rule_version_id,
        location=TextRangeLocation(
            kind="text_range",
            start_offset=0,
            end_offset=5,
            matched_text="cheap",
        ),
        suggested_correction="affordable",
        detection_method=DetectionMethod.DETERMINISTIC,
        requires_human_review=True,
    )

    output = finding.model_dump(mode="json")

    expected_fields = {
        "id",
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
    }

    assert set(output.keys()) == expected_fields
    assert output["category"] == "terminology"
    assert output["severity"] == "medium"
    assert output["result"] == "conflict"
    assert output["detection_method"] == "deterministic"
    assert output["location"]["start_offset"] == 0
    assert output["location"]["end_offset"] == 5
    assert output["source_rule_version_id"] == str(rule_version_id)
    assert output["source_fact_version_id"] is None


def test_summary_counts_findings_by_severity():
    findings = [
        Finding(
            category=FindingCategory.TERMINOLOGY,
            severity=Severity.MEDIUM,
            result=FindingResult.CONFLICT,
            explanation="First issue.",
            detection_method=DetectionMethod.DETERMINISTIC,
        ),
        Finding(
            category=FindingCategory.FACTUAL_CLAIM,
            severity=Severity.HIGH,
            result=FindingResult.CONFLICT,
            explanation="Second issue.",
            detection_method=DetectionMethod.DETERMINISTIC,
        ),
        Finding(
            category=FindingCategory.TONE,
            severity=Severity.INFO,
            result=FindingResult.INCONCLUSIVE,
            explanation="Third issue.",
            detection_method=DetectionMethod.AI_ASSISTED,
        ),
    ]

    summary = build_summary(findings)

    assert summary.info == 1
    assert summary.low == 0
    assert summary.medium == 1
    assert summary.high == 1
    assert summary.total == 3


def test_image_location_uses_normalised_coordinates():
    location = ImageBoundingBoxLocation(
        kind="image_bbox",
        x=0.1,
        y=0.2,
        width=0.3,
        height=0.1,
    )

    assert location.x == 0.1
    assert location.width == 0.3


def test_analysis_response_has_submission_version():
    job_id = uuid4()
    submission_id = uuid4()
    version_id = uuid4()

    response = AnalysisResponse(
        job_id=job_id,
        submission_id=submission_id,
        submission_version_id=version_id,
        status="completed",
        findings=[],
        summary=build_summary([]),
    )

    output = response.model_dump(mode="json")

    assert output["job_id"] == str(job_id)
    assert output["submission_id"] == str(submission_id)
    assert output["submission_version_id"] == str(version_id)
    assert output["status"] == "completed"
    assert output["findings"] == []
    assert output["summary"]["total"] == 0
    