
import json
from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from app.analysis.claims import (
    StructuredApprovedFact,
    StructuredClaim,
    check_claims,
)
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
    """Create a stable signature for report-level deduplication."""

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

    return json.dumps(signature, sort_keys=True, ensure_ascii=False)


def aggregate_findings(
    *finding_groups: Sequence[Finding],
) -> list[Finding]:
    """Combine findings and remove logical duplicates within one report."""

    aggregated: list[Finding] = []
    seen: set[str] = set()

    for group in finding_groups:
        for finding in group:
            signature = _finding_signature(finding)

            if signature not in seen:
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
    """Construct the response defined by analysis-result.md."""

    combined = aggregate_findings(findings)

    return AnalysisResponse(
        job_id=job_id,
        submission_id=submission_id,
        submission_version_id=submission_version_id,
        status=status,
        findings=combined,
        summary=build_summary(combined),
    )


def _unavailable_finding(
    *,
    category: FindingCategory,
    explanation: str,
    source_name: str,
) -> Finding:
    """Represent a check that could not be completed."""

    return Finding(
        category=category,
        severity=Severity.INFO,
        result=FindingResult.CHECK_UNAVAILABLE,
        explanation=explanation,
        evidence=Evidence(source_name=source_name),
        detection_method=DetectionMethod.DETERMINISTIC,
        requires_human_review=True,
    )


def run_terminology_slice(
    *,
    job_id: UUID,
    submission_id: UUID,
    submission_version_id: UUID,
    content_text: str,
    terminology_rules: Sequence[ApprovedTerminologyRule],
) -> AnalysisResponse:
    """Run the initial terminology-only analysis slice."""

    if not terminology_rules:
        finding = _unavailable_finding(
            category=FindingCategory.TERMINOLOGY,
            explanation=(
                "No applicable approved terminology rules were supplied; "
                "terminology compliance could not be assessed."
            ),
            source_name="Approved terminology rules",
        )

        return build_analysis_response(
            job_id=job_id,
            submission_id=submission_id,
            submission_version_id=submission_version_id,
            findings=[finding],
            status="partial",
        )

    findings = check_terminology(content_text, terminology_rules)

    return build_analysis_response(
        job_id=job_id,
        submission_id=submission_id,
        submission_version_id=submission_version_id,
        findings=findings,
        status="completed",
    )


def run_analysis(
    *,
    job_id: UUID,
    submission_id: UUID,
    submission_version_id: UUID,
    content_text: str,
    terminology_rules: Sequence[ApprovedTerminologyRule] | None,
    claims: Sequence[StructuredClaim] | None,
    approved_facts: Sequence[StructuredApprovedFact] = (),
    fact_lookup_completed: bool = False,
    requested_checks: dict[str, bool] | None = None,
) -> AnalysisResponse:
    """
    Run the currently implemented terminology and claim checks.

    None means the corresponding input/check is unavailable.
    An empty claims list means claim extraction completed but found
    no claim candidates.

    The caller must retrieve applicable approved records using the
    trusted organisation context and must not supply unapproved
    records to this function.
    """

    findings: list[Finding] = []

    # 1. Terminology check
    if (
        requested_checks is not None
        and requested_checks.get("terminology") is not True
    ):
        # This check was not requested; don't report it as unavailable.
        pass
    elif not terminology_rules:
        findings.append(
            _unavailable_finding(
                category=FindingCategory.TERMINOLOGY,
                explanation=(
                    "No applicable approved terminology rules were "
                    "supplied; terminology compliance could not be assessed."
                ),
                source_name="Approved terminology rules",
            )
        )
    else:
        findings.extend(
            check_terminology(content_text, terminology_rules)
        )
       # 2. Claim extraction and approved-fact comparison
    if (
        requested_checks is not None
        and requested_checks.get("factual_claim") is not True
    ):
        # This check was not requested; don't report it as unavailable.
        pass

    elif claims is None:
        findings.append(
            _unavailable_finding(
                category=FindingCategory.FACTUAL_CLAIM,
                explanation=(
                    "Structured claim extraction was unavailable, so "
                    "claim verification could not be completed."
                ),
                source_name="Claim extraction",
            )
        )

    elif claims:
        # Claim locations must refer to the exact content being analysed.
        matching_claims = [
            claim
            for claim in claims
            if claim.source_text == content_text
        ]

        has_mismatched_source = len(matching_claims) != len(claims)

        if has_mismatched_source:
            findings.append(
                _unavailable_finding(
                    category=FindingCategory.FACTUAL_CLAIM,
                    explanation=(
                        "One or more extracted claims refer to text "
                        "that does not match the submitted content. "
                        "Those claims could not be reliably checked."
                    ),
                    source_name="Claim extraction",
                )
            )

        if matching_claims:
            findings.extend(
                check_claims(
                    matching_claims,
                    approved_facts,
                    fact_lookup_completed=fact_lookup_completed,
                )
            )

    # An inconclusive result is still an evaluated check.
    # An unavailable check means the overall analysis is partial.
    combined = aggregate_findings(findings)
    status: Literal["completed", "partial"] = (
        "partial"
        if any(
            item.result == FindingResult.CHECK_UNAVAILABLE
            for item in combined
        )
        else "completed"
    )

    return build_analysis_response(
        job_id=job_id,
        submission_id=submission_id,
        submission_version_id=submission_version_id,
        findings=combined,
        status=status,
    )
