
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
    CheckOutcome,
    CheckOutcomeStatus,
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
    check_outcomes: Sequence[CheckOutcome] = (),
) -> AnalysisResponse:
    """Construct a response with findings and explicit check coverage."""

    combined = aggregate_findings(findings)

    return AnalysisResponse(
        job_id=job_id,
        submission_id=submission_id,
        submission_version_id=submission_version_id,
        status=status,
        findings=combined,
        check_outcomes=list(check_outcomes),
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


def _terminology_outcome(
    findings: Sequence[Finding],
    *,
    assessed_count: int,
) -> CheckOutcome:
    """Describe the result of the configured terminology rules."""

    has_unavailable = any(
        finding.result == FindingResult.CHECK_UNAVAILABLE
        for finding in findings
    )

    if has_unavailable:
        status = CheckOutcomeStatus.CHECK_UNAVAILABLE
        message = (
            "Terminology compliance could not be fully assessed "
            "because the check was unavailable."
        )
    elif findings:
        status = CheckOutcomeStatus.ISSUES_FOUND
        message = (
            "One or more supplied approved terminology rules "
            "were not satisfied."
        )
    else:
        status = CheckOutcomeStatus.SUPPORTED
        message = (
            "All supplied approved terminology rules passed. "
            "This outcome covers only the rules provided to the checker."
        )

    return CheckOutcome(
        category=FindingCategory.TERMINOLOGY,
        status=status,
        message=message,
        detection_method=DetectionMethod.DETERMINISTIC,
        assessed_count=assessed_count,
        scope="supplied_approved_terminology_rules",
    )


def _claim_outcome(
    claim_findings: Sequence[Finding],
    *,
    assessed_count: int,
    extracted_count: int,
    source_mismatch: bool = False,
) -> CheckOutcome:
    """Describe claim-check coverage without implying broader coverage."""

    has_unavailable = any(
        finding.result == FindingResult.CHECK_UNAVAILABLE
        for finding in claim_findings
    )
    has_inconclusive = any(
        finding.result == FindingResult.INCONCLUSIVE
        for finding in claim_findings
    )
    has_issues = any(
        finding.result
        in {
            FindingResult.CONFLICT,
            FindingResult.UNSUPPORTED,
        }
        for finding in claim_findings
    )

    if has_unavailable:
        status = CheckOutcomeStatus.CHECK_UNAVAILABLE
        message = (
            "One or more extracted structured claims could not be "
            "reliably checked. Review the related findings."
        )
    elif source_mismatch:
        status = CheckOutcomeStatus.COVERAGE_LIMITED
        message = (
            f"Only {assessed_count} of {extracted_count} extracted "
            "structured claims were assessed because one or more "
            "claims did not reference the exact submitted text."
        )
    elif has_inconclusive:
        status = CheckOutcomeStatus.INCONCLUSIVE
        message = (
            "One or more extracted structured claims had ambiguous "
            "approved evidence and require human verification."
        )
    elif has_issues:
        status = CheckOutcomeStatus.ISSUES_FOUND
        message = (
            "One or more extracted structured claims conflicted with "
            "approved facts or lacked an applicable approved fact."
        )
    else:
        status = CheckOutcomeStatus.SUPPORTED
        message = (
            "All extracted supported structured claims matched the "
            "applicable approved facts. Broader natural-language factual "
            "claims were not assessed by this structured-claim check."
        )

    return CheckOutcome(
        category=FindingCategory.FACTUAL_CLAIM,
        status=status,
        message=message,
        detection_method=DetectionMethod.DETERMINISTIC,
        assessed_count=assessed_count,
        scope="supported_structured_claims_only",
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

        outcome = CheckOutcome(
            category=FindingCategory.TERMINOLOGY,
            status=CheckOutcomeStatus.CHECK_UNAVAILABLE,
            message=(
                "No applicable approved terminology rules were supplied. "
                "Terminology compliance was not assessed."
            ),
            detection_method=DetectionMethod.DETERMINISTIC,
            assessed_count=0,
            scope="supplied_approved_terminology_rules",
        )

        return build_analysis_response(
            job_id=job_id,
            submission_id=submission_id,
            submission_version_id=submission_version_id,
            findings=[finding],
            status="partial",
            check_outcomes=[outcome],
        )

    findings = check_terminology(content_text, terminology_rules)
    outcome = _terminology_outcome(
        findings,
        assessed_count=len(terminology_rules),
    )

    return build_analysis_response(
        job_id=job_id,
        submission_id=submission_id,
        submission_version_id=submission_version_id,
        findings=findings,
        status="completed",
        check_outcomes=[outcome],
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
) -> AnalysisResponse:
    """
    Run the currently implemented terminology and structured-claim checks.

    None means the corresponding input/check is unavailable.
    An empty claims list means extraction ran but found no supported
    structured claims. It does not mean the content has no factual claims.

    The caller must retrieve applicable approved records using the trusted
    organisation context and must not supply unapproved records.
    """

    findings: list[Finding] = []
    check_outcomes: list[CheckOutcome] = []

    # 1. Terminology check
    if not terminology_rules:
        finding = _unavailable_finding(
            category=FindingCategory.TERMINOLOGY,
            explanation=(
                "No applicable approved terminology rules were supplied; "
                "terminology compliance could not be assessed."
            ),
            source_name="Approved terminology rules",
        )
        findings.append(finding)

        check_outcomes.append(
            CheckOutcome(
                category=FindingCategory.TERMINOLOGY,
                status=CheckOutcomeStatus.CHECK_UNAVAILABLE,
                message=(
                    "No applicable approved terminology rules were supplied. "
                    "Terminology compliance was not assessed."
                ),
                detection_method=DetectionMethod.DETERMINISTIC,
                assessed_count=0,
                scope="supplied_approved_terminology_rules",
            )
        )
    else:
        terminology_findings = check_terminology(
            content_text,
            terminology_rules,
        )
        findings.extend(terminology_findings)
        check_outcomes.append(
            _terminology_outcome(
                terminology_findings,
                assessed_count=len(terminology_rules),
            )
        )

    # 2. Claim extraction and approved-fact comparison
    if claims is None:
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

        check_outcomes.append(
            CheckOutcome(
                category=FindingCategory.FACTUAL_CLAIM,
                status=CheckOutcomeStatus.CHECK_UNAVAILABLE,
                message=(
                    "Structured claim extraction was unavailable. "
                    "Factual-claim verification could not be completed."
                ),
                detection_method=DetectionMethod.DETERMINISTIC,
                assessed_count=0,
                scope="supported_structured_claims_only",
            )
        )

    elif not claims:
        # Do not treat an empty extraction result as a factual pass.
        check_outcomes.append(
            CheckOutcome(
                category=FindingCategory.FACTUAL_CLAIM,
                status=CheckOutcomeStatus.COVERAGE_LIMITED,
                message=(
                    "No supported structured numeric claims were extracted. "
                    "Broader natural-language factual claims were not "
                    "assessed by this check."
                ),
                detection_method=DetectionMethod.DETERMINISTIC,
                assessed_count=0,
                scope="supported_structured_claims_only",
            )
        )

    else:
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
                        "One or more extracted claims refer to text that "
                        "does not match the submitted content. Those claims "
                        "could not be reliably checked."
                    ),
                    source_name="Claim extraction",
                )
            )

        claim_findings: list[Finding] = []

        if matching_claims:
            claim_findings = check_claims(
                matching_claims,
                approved_facts,
                fact_lookup_completed=fact_lookup_completed,
            )
            findings.extend(claim_findings)

        # An outcome describes the scope actually assessed, including any
        # claims excluded because their source text did not match.
        check_outcomes.append(
            _claim_outcome(
                claim_findings,
                assessed_count=len(matching_claims),
                extracted_count=len(claims),
                source_mismatch=has_mismatched_source,
            )
        )

    # A partial result signals unavailable or limited check coverage.
    # Conflicts and inconclusive findings can still be results of completed
    # checks and do not alone make the overall run partial.
    combined = aggregate_findings(findings)
    coverage_limited_statuses = {
        CheckOutcomeStatus.CHECK_UNAVAILABLE,
        CheckOutcomeStatus.COVERAGE_LIMITED,
        CheckOutcomeStatus.DISABLED,
        CheckOutcomeStatus.NOT_ASSESSED,
    }

    status: Literal["completed", "partial"] = (
        "partial"
        if (
            any(
                outcome.status in coverage_limited_statuses
                for outcome in check_outcomes
            )
            or any(
                finding.result == FindingResult.CHECK_UNAVAILABLE
                for finding in combined
            )
        )
        else "completed"
    )

    return build_analysis_response(
        job_id=job_id,
        submission_id=submission_id,
        submission_version_id=submission_version_id,
        findings=combined,
        status=status,
        check_outcomes=check_outcomes,
    )
