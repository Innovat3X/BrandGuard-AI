"""Bridge approved database knowledge to the content-analysis pipeline."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.analysis.contracts import (
    AnalysisResponse,
    DetectionMethod,
    Evidence,
    Finding,
    FindingCategory,
    FindingResult,
    Severity,
)
from app.analysis.pipeline import aggregate_findings, build_analysis_response
from app.infrastructure.db.analysis_knowledge_loader import (
    ApprovedFactVersionRecord,
    ApprovedRuleVersionRecord,
    DatabaseAnalysisKnowledgeLoader,
)


class AnalysisPipelineContext(Protocol):
    """Context supplied by the analysis worker."""

    job_id: UUID
    organization_id: UUID
    submission_id: UUID
    submission_version_id: UUID
    content_text: str
    requested_checks: dict[str, Any] | list[Any] | None


@dataclass(frozen=True)
class AiGuideline:
    """Approved guideline data passed to the AI provider."""

    source_rule_version_id: UUID
    category: str
    rule_text: str
    severity: Severity


class AiAnalysisProvider(Protocol):
    """Provider interface independent of the chosen AI vendor."""

    def analyze(
        self,
        *,
        content_text: str,
        approved_guidelines: Sequence[AiGuideline],
    ) -> list[Finding]:
        """Return validated findings or explicit unavailable findings."""
        ...


class AnalysisRunner(Protocol):
    """Callable interface implemented by the analysis pipeline."""

    def __call__(
        self,
        *,
        job_id: UUID,
        submission_id: UUID,
        submission_version_id: UUID,
        content_text: str,
        terminology_rules: Sequence[Any] | None,
        claims: Sequence[Any] | None,
        approved_facts: Sequence[Any],
        fact_lookup_completed: bool,
        requested_checks: dict[str, bool] | None = None,
    ) -> AnalysisResponse:
        ...


RuleMapper = Callable[
    [Sequence[ApprovedRuleVersionRecord]],
    Sequence[Any] | None,
]

FactMapper = Callable[
    [Sequence[ApprovedFactVersionRecord]],
    Sequence[Any] | None,
]

ClaimExtractor = Callable[
    [str],
    Sequence[Any] | None,
]

SUPPORTED_CHECKS = (
    "tone",
    "messaging",
    "terminology",
    "factual_claim",
)

AI_CHECKS = ("tone", "messaging")


def _normalize_requested_checks(
    requested_checks: dict[str, Any] | list[Any] | None,
) -> dict[str, bool] | None:
    """Normalize supported check selections without changing defaults.

    None preserves the existing behavior: all currently implemented
    checks are eligible to run.

    A dictionary uses Boolean values. A list is treated as a list of
    selected check names for compatibility with older stored requests.
    """

    if requested_checks is None:
        return None

    if isinstance(requested_checks, dict):
        return {
            check_name: requested_checks.get(check_name, False) is True
            for check_name in SUPPORTED_CHECKS
        }

    if isinstance(requested_checks, list):
        return {
            check_name: check_name in requested_checks
            for check_name in SUPPORTED_CHECKS
        }

    raise ValueError("requested_checks must be a dictionary, list, or None.")


def _is_check_enabled(
    requested_checks: dict[str, bool] | None,
    check_name: str,
) -> bool:
    """Return whether a check is enabled under the normalized selection."""

    # An omitted selection retains the old default behavior.
    if requested_checks is None:
        return True

    return requested_checks.get(check_name, False)


class DatabaseAnalysisPipeline:
    """Load approved knowledge and run selected deterministic and AI checks."""

    def __init__(
        self,
        *,
        knowledge_loader: DatabaseAnalysisKnowledgeLoader,
        analysis_runner: AnalysisRunner,
        rule_mapper: RuleMapper | None = None,
        fact_mapper: FactMapper | None = None,
        claim_extractor: ClaimExtractor | None = None,
        ai_analysis_provider: AiAnalysisProvider | None = None,
    ) -> None:
        self._knowledge_loader = knowledge_loader
        self._analysis_runner = analysis_runner
        self._rule_mapper = rule_mapper
        self._fact_mapper = fact_mapper
        self._claim_extractor = claim_extractor
        self._ai_analysis_provider = ai_analysis_provider

    def analyze(self, context: AnalysisPipelineContext) -> AnalysisResponse:
        """Analyse one submission version using approved organisation data."""

        # getattr provides compatibility with lightweight contexts in tests
        # and older internal callers that don't define this attribute.
        raw_requested_checks = getattr(context, "requested_checks", None)
        requested_checks = _normalize_requested_checks(
            raw_requested_checks
        )

        terminology_enabled = _is_check_enabled(
            requested_checks,
            "terminology",
        )
        factual_claim_enabled = _is_check_enabled(
            requested_checks,
            "factual_claim",
        )

        selected_ai_checks = tuple(
            check_name
            for check_name in AI_CHECKS
            if _is_check_enabled(requested_checks, check_name)
        )

        knowledge = self._knowledge_loader.load(
            organization_id=context.organization_id,
        )

        # Don't invoke the terminology mapper when that check was disabled.
        terminology_rules = (
            self._rule_mapper(knowledge.rule_versions)
            if terminology_enabled and self._rule_mapper is not None
            else None
        )

        # Don't extract claims or map facts for a disabled factual check.
        claims = (
            self._claim_extractor(context.content_text)
            if factual_claim_enabled and self._claim_extractor is not None
            else None
        )

        mapped_facts = (
            self._fact_mapper(knowledge.fact_versions)
            if factual_claim_enabled and self._fact_mapper is not None
            else None
        )

        runner_kwargs: dict[str, Any] = {
            "job_id": context.job_id,
            "submission_id": context.submission_id,
            "submission_version_id": context.submission_version_id,
            "content_text": context.content_text,
            "terminology_rules": terminology_rules,
            "claims": claims,
            "approved_facts": (
                mapped_facts if mapped_facts is not None else ()
            ),
            "fact_lookup_completed": (
                mapped_facts is not None if factual_claim_enabled else False
            ),
        }

        # Preserve compatibility with existing custom runners and retain
        # their default behavior when no check selection was supplied.
        if requested_checks is not None:
            runner_kwargs["requested_checks"] = requested_checks

        deterministic_result = self._analysis_runner(**runner_kwargs)

        # Don't call the AI provider if neither AI check was selected.
        if not selected_ai_checks:
            return deterministic_result

        # Preserve existing default behavior when checks were not specified:
        # AI remains optional and is only used when a provider is injected.
        if self._ai_analysis_provider is None:
            if requested_checks is None:
                return deterministic_result

            ai_findings = self._build_unavailable_ai_findings(
                selected_ai_checks
            )
        else:
            # When the caller selects specific AI categories, pass only
            # guidelines for those categories. For the default path, retain
            # the existing set of guidelines supplied to the AI provider.
            guideline_categories = (
                set(selected_ai_checks)
                if requested_checks is not None
                else None
            )

            approved_guidelines = self._build_ai_guidelines(
                knowledge.rule_versions,
                categories=guideline_categories,
            )

            provider_findings = self._ai_analysis_provider.analyze(
                content_text=context.content_text,
                approved_guidelines=approved_guidelines,
            )

            # The current provider may return unavailable results for both
            # AI categories. Never include results for a disabled category.
            ai_findings = [
                finding
                for finding in provider_findings
                if finding.category.value in selected_ai_checks
            ]

        combined_findings = aggregate_findings(
            deterministic_result.findings,
            ai_findings,
        )

        status = (
            "partial"
            if (
                deterministic_result.status == "partial"
                or any(
                    finding.result == FindingResult.CHECK_UNAVAILABLE
                    for finding in combined_findings
                )
            )
            else "completed"
        )

        return build_analysis_response(
            job_id=context.job_id,
            submission_id=context.submission_id,
            submission_version_id=context.submission_version_id,
            findings=combined_findings,
            status=status,
        )

    @staticmethod
    def _build_unavailable_ai_findings(
        categories: Sequence[str],
    ) -> list[Finding]:
        """Mark explicitly requested AI checks unavailable when unconfigured."""

        return [
            Finding(
                category=FindingCategory(category),
                severity=Severity.INFO,
                result=FindingResult.CHECK_UNAVAILABLE,
                explanation=(
                    f"The {category.replace('_', ' ')} check was requested, "
                    "but no AI analysis provider is configured. This check "
                    "was not completed and must not be treated as passed."
                ),
                evidence=Evidence(
                    source_name="AI brand analysis provider",
                ),
                detection_method=DetectionMethod.AI_ASSISTED,
                requires_human_review=True,
            )
            for category in categories
        ]

    @staticmethod
    def _build_ai_guidelines(
        rule_versions: Sequence[ApprovedRuleVersionRecord],
        *,
        categories: set[str] | None = None,
    ) -> list[AiGuideline]:
        """Convert loaded, approved rules into AI prompt context.

        If categories is specified, ignore rules belonging to other
        categories. Only approved records loaded for the organisation
        are eligible for inclusion.
        """

        guidelines: list[AiGuideline] = []

        for rule in rule_versions:
            if categories is not None and rule.category not in categories:
                continue

            try:
                severity = Severity(rule.severity)
            except ValueError as exc:
                raise ValueError(
                    f"Approved rule version {rule.version_id} has "
                    f"unsupported severity {rule.severity!r}."
                ) from exc

            guidelines.append(
                AiGuideline(
                    source_rule_version_id=rule.version_id,
                    category=rule.category,
                    rule_text=rule.rule_text,
                    severity=severity,
                )
            )

        return guidelines