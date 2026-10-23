import json
from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from app.analysis.contracts import (
    AnalysisResponse,
    DetectionMethod,
    Evidence,
    Finding,
    FindingCategory,
    FindingResult,
    Severity,
    build_summary,
)
from app.analysis.terminology import (
    ApprovedTerminologyRule,
    check_terminology,
)


def _finding_signature(finding: Finding) -> str:
    """Create a stable signature for logical finding deduplication."""

    signature = {
        "category": finding.category.value,
        "severity": finding.severity.value,
        "result": finding.result.value,
        "rule_version": (
            str(finding.source_rule_version_id)
            if finding.source_rule_version_id
            else None
        ),
        "fact_version": (
            str(finding.source_fact_version_id)
            if finding.source_fact_version_id
            else None
        ),
        "detection_method": finding.detection_method.value,
        "location": (
            finding.location.model_dump(mode="json")
            if finding.location is not None
            else None
        ),
        "submitted_text": finding.evidence.submitted_text,
        "approved_reference": finding.evidence.approved_reference,
        "suggested_correction": finding.suggested_correction,
    }

    return json.dumps(
        signature,
        sort_keys=True,
        ensure_ascii=False,
    )


def aggregate_findings(
    *finding_groups: Sequence[Finding],
) -> list[Finding]:
    """Combine finding groups and remove logical duplicates."""

    aggregated: list[Finding] = []
    seen: set[str] = set()

    for group in finding_groups:
        for finding in group:
            signature = _finding_signature(finding)

            if signature in seen:
                continue

            seen.add(signature)
            aggregated.append(finding)

    return aggregated


def build_analysis_response(
    *,
    job_id: UUID,
    submission_id: UUID,
    submission_version_id: UUID,
    findings: Sequence[Finding],
    status: Literal["completed", "partial"],
) -> AnalysisResponse:
    """Build the response using the shared analysis-result contract."""

    combined = aggregate_findings(findings)

    return AnalysisResponse(
        job_id=job_id,
        submission_id=submission_id,
        submission_version_id=submission_version_id,
        status=status,
        findings=combined,
        summary=build_summary(combined),
    )


def run_terminology_slice(
    *,
    job_id: UUID,
    submission_id: UUID,
    submission_version_id: UUID,
    content_text: str,
    terminology_rules: Sequence[ApprovedTerminologyRule],
) -> AnalysisResponse:
    """
    Run the first terminology-only analysis slice.

    This is not yet the full brand-governance pipeline.
    """

    if not terminology_rules:
        finding = Finding(
            category=FindingCategory.TERMINOLOGY,
            severity=Severity.INFO,
            result=FindingResult.CHECK_UNAVAILABLE,
            explanation=(
                "No applicable approved terminology rules were "
                "supplied, so terminology compliance could not "
                "be assessed."
            ),
            evidence=Evidence(
                source_name="Approved terminology rules",
            ),
            detection_method=DetectionMethod.DETERMINISTIC,
            requires_human_review=True,
        )

        return build_analysis_response(
            job_id=job_id,
            submission_id=submission_id,
            submission_version_id=submission_version_id,
            findings=[finding],
            status="partial",
        )

    findings = check_terminology(
        content_text,
        terminology_rules,
    )

    return build_analysis_response(
        job_id=job_id,
        submission_id=submission_id,
        submission_version_id=submission_version_id,
        findings=findings,
        status="completed",
    )