"""Bridge approved database knowledge to the content-analysis pipeline."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

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
)
from app.analysis.pipeline import aggregate_findings, build_analysis_response
from app.infrastructure.db.analysis_knowledge_loader import (
    ApprovedFactVersionRecord,
    ApprovedRuleVersionRecord,
    DatabaseAnalysisKnowledgeLoader,
)


SUPPORTED_CHECKS = (
    "tone",
    "messaging",
    "terminology",
    "factual_claim",
)

AI_CHECKS = (
    "tone",
    "messaging",
)

_AI_CATEGORIES = (
    FindingCategory.TONE,
    FindingCategory.MESSAGING,
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


def _normalize_requested_checks(
    requested_checks: dict[str, Any] | list[Any] | None,
) -> dict[str, bool] | None:
    """Normalize requested checks while preserving default behaviour.

    None means the caller did not specify a selection and preserves the
    existing default behaviour.

    A dictionary uses boolean values. Missing keys become false.

    A list is supported for compatibility with older persisted requests
    where the list contains the names of selected checks.
    """

    if requested_checks is None:
        return None

    if isinstance(requested_checks, dict):
        return {
            check_name: requested_checks.get(check_name) is True
            for check_name in SUPPORTED_CHECKS
        }

    if isinstance(requested_checks, list):
        return {
            check_name: check_name in requested_checks
            for check_name in SUPPORTED_CHECKS
        }

    raise ValueError(
        "requested_checks must be a dictionary, list, or None."
    )


def _is_check_enabled(
    requested_checks: dict[str, bool] | None,
    check_name: str,
) -> bool:
    """Return whether a check is enabled under the normalized selection."""

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

        # Lightweight contexts and older callers may not define this field.
        raw_requested_checks = getattr(
            context,
            "requested_checks",
            None,
        )

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

        # Do not invoke the terminology mapper when terminology was disabled.
        terminology_rules = (
            self._rule_mapper(knowledge.rule_versions)
            if (
                terminology_enabled
                and self._rule_mapper is not None
            )
            else None
        )

        # Do not extract claims or map approved facts when factual analysis
        # was disabled.
        claims = (
            self._claim_extractor(context.content_text)
            if (
                factual_claim_enabled
                and self._claim_extractor is not None
            )
            else None
        )

        mapped_facts = (
            self._fact_mapper(knowledge.fact_versions)
            if (
                factual_claim_enabled
                and self._fact_mapper is not None
            )
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
                mapped_facts is not None
                if factual_claim_enabled
                else False
            ),
        }

        # Preserve compatibility with old custom runners when the caller
        # omitted requested_checks entirely.
        if requested_checks is not None:
            runner_kwargs["requested_checks"] = requested_checks

        deterministic_result = self._analysis_runner(**runner_kwargs)

        # Default behaviour: no explicit selections were supplied.
        # Keep the existing optional-AI behaviour unchanged.
        if requested_checks is None:
            if self._ai_analysis_provider is None:
                return self._mark_ai_checks_disabled(
                    deterministic_result
                )

            return self._run_default_ai_checks(
                context=context,
                knowledge=knowledge,
                deterministic_result=deterministic_result,
            )

        # Explicit selection: build outcomes for intentionally unselected
        # AI categories, without treating them as incomplete coverage.
        disabled_ai_outcomes = self._build_disabled_ai_outcomes(
            selected_ai_checks
        )

        # Do not invoke the AI provider when neither AI check was selected.
        if not selected_ai_checks:
            return self._combine_explicit_results(
                context=context,
                deterministic_result=deterministic_result,
                ai_findings=[],
                ai_outcomes=[],
                disabled_ai_outcomes=disabled_ai_outcomes,
            )

        # A selected AI check without a configured provider is unavailable,
        # not passed and not silently disabled.
        if self._ai_analysis_provider is None:
            ai_findings = self._build_unavailable_ai_findings(
                selected_ai_checks
            )

            ai_outcomes = self._build_ai_check_outcomes(
                ai_findings,
                categories=tuple(
                    FindingCategory(name)
                    for name in selected_ai_checks
                ),
                guideline_count=0,
            )

            return self._combine_explicit_results(
                context=context,
                deterministic_result=deterministic_result,
                ai_findings=ai_findings,
                ai_outcomes=ai_outcomes,
                disabled_ai_outcomes=disabled_ai_outcomes,
            )

        # Only pass approved guidelines belonging to the selected AI checks.
        approved_guidelines = self._build_ai_guidelines(
            knowledge.rule_versions,
            categories=set(selected_ai_checks),
        )

        provider_findings = self._ai_analysis_provider.analyze(
            content_text=context.content_text,
            approved_guidelines=approved_guidelines,
        )

        # Never retain results for an AI category that was not selected.
        ai_findings = [
            finding.model_copy(
                update={"requires_human_review": True}
            )
            for finding in provider_findings
            if finding.category.value in selected_ai_checks
        ]

        ai_categories = tuple(
            FindingCategory(name)
            for name in selected_ai_checks
        )

        ai_outcomes = self._build_ai_check_outcomes(
            ai_findings,
            categories=ai_categories,
            guideline_count=len(approved_guidelines),
        )

        return self._combine_explicit_results(
            context=context,
            deterministic_result=deterministic_result,
            ai_findings=ai_findings,
            ai_outcomes=ai_outcomes,
            disabled_ai_outcomes=disabled_ai_outcomes,
        )

    def _run_default_ai_checks(
        self,
        *,
        context: AnalysisPipelineContext,
        knowledge: Any,
        deterministic_result: AnalysisResponse,
    ) -> AnalysisResponse:
        """Run both AI checks when the request uses the legacy default."""

        approved_guidelines = self._build_ai_guidelines(
            knowledge.rule_versions
        )

        provider_findings = self._ai_analysis_provider.analyze(
            content_text=context.content_text,
            approved_guidelines=approved_guidelines,
        )

        ai_findings = [
            finding.model_copy(
                update={"requires_human_review": True}
            )
            for finding in provider_findings
        ]

        combined_findings = aggregate_findings(
            deterministic_result.findings,
            ai_findings,
        )

        deterministic_outcomes = [
            outcome
            for outcome in deterministic_result.check_outcomes
            if outcome.category not in _AI_CATEGORIES
        ]

        ai_outcomes = self._build_ai_check_outcomes(
            ai_findings,
            categories=_AI_CATEGORIES,
            guideline_count=len(approved_guidelines),
        )

        combined_outcomes = [
            *deterministic_outcomes,
            *ai_outcomes,
        ]

        status = self._calculate_final_status(
            deterministic_status=deterministic_result.status,
            findings=combined_findings,
            outcomes=combined_outcomes,
        )

        return build_analysis_response(
            job_id=context.job_id,
            submission_id=context.submission_id,
            submission_version_id=context.submission_version_id,
            findings=combined_findings,
            status=status,
            check_outcomes=combined_outcomes,
        )

    def _combine_explicit_results(
        self,
        *,
        context: AnalysisPipelineContext,
        deterministic_result: AnalysisResponse,
        ai_findings: Sequence[Finding],
        ai_outcomes: Sequence[CheckOutcome],
        disabled_ai_outcomes: Sequence[CheckOutcome],
    ) -> AnalysisResponse:
        """Combine deterministic and explicitly selected AI check results."""

        combined_findings = aggregate_findings(
            deterministic_result.findings,
            ai_findings,
        )

        # Preserve every deterministic outcome. Add AI outcomes for selected
        # categories and DISABLED outcomes for intentionally unselected ones.
        combined_outcomes = [
            *deterministic_result.check_outcomes,
            *ai_outcomes,
            *disabled_ai_outcomes,
        ]

        status = self._calculate_final_status(
            deterministic_status=deterministic_result.status,
            findings=combined_findings,
            outcomes=combined_outcomes,
        )

        return build_analysis_response(
            job_id=context.job_id,
            submission_id=context.submission_id,
            submission_version_id=context.submission_version_id,
            findings=combined_findings,
            status=status,
            check_outcomes=combined_outcomes,
        )

    @staticmethod
    def _calculate_final_status(
        *,
        deterministic_status: str,
        findings: Sequence[Finding],
        outcomes: Sequence[CheckOutcome],
    ) -> str:
        """Calculate status from actual coverage of requested checks."""

        incomplete_statuses = {
            CheckOutcomeStatus.CHECK_UNAVAILABLE,
            CheckOutcomeStatus.COVERAGE_LIMITED,
            CheckOutcomeStatus.NOT_ASSESSED,
        }

        is_partial = (
            deterministic_status == "partial"
            or any(
                finding.result == FindingResult.CHECK_UNAVAILABLE
                for finding in findings
            )
            or any(
                outcome.status in incomplete_statuses
                for outcome in outcomes
            )
        )

        return "partial" if is_partial else "completed"

    @staticmethod
    def _mark_ai_checks_disabled(
        result: AnalysisResponse,
    ) -> AnalysisResponse:
        """Preserve legacy default behaviour when no AI provider is configured."""

        # Keep non-contract test doubles and custom runner results unchanged.
        if not isinstance(result, AnalysisResponse):
            return result

        existing_outcomes = [
            outcome
            for outcome in result.check_outcomes
            if outcome.category not in _AI_CATEGORIES
        ]

        disabled_outcomes = [
            CheckOutcome(
                category=category,
                status=CheckOutcomeStatus.DISABLED,
                message=(
                    f"The {category.value} check is disabled because no "
                    "AI analysis provider is configured. This category "
                    "was not assessed."
                ),
                detection_method=None,
                assessed_count=0,
                scope="optional_ai_brand_analysis",
            )
            for category in _AI_CATEGORIES
        ]

        combined_outcomes = [
            *existing_outcomes,
            *disabled_outcomes,
        ]

        final_status = DatabaseAnalysisPipeline._calculate_final_status(
            deterministic_status=result.status,
            findings=result.findings,
            outcomes=combined_outcomes,
        )

        return build_analysis_response(
            job_id=result.job_id,
            submission_id=result.submission_id,
            submission_version_id=result.submission_version_id,
            findings=result.findings,
            status=final_status,
            check_outcomes=combined_outcomes,
        )

    @staticmethod
    def _build_disabled_ai_outcomes(
        selected_ai_checks: Sequence[str],
    ) -> list[CheckOutcome]:
        """Describe AI checks intentionally excluded from this request."""

        selected = set(selected_ai_checks)
        outcomes: list[CheckOutcome] = []

        for category in _AI_CATEGORIES:
            if category.value in selected:
                continue

            outcomes.append(
                CheckOutcome(
                    category=category,
                    status=CheckOutcomeStatus.DISABLED,
                    message=(
                        f"The {category.value} check was not selected "
                        "for this analysis. It was intentionally "
                        "not assessed."
                    ),
                    detection_method=None,
                    assessed_count=0,
                    scope="not_requested",
                )
            )

        return outcomes

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
    def _build_ai_check_outcomes(
        ai_findings: Sequence[Finding],
        *,
        categories: Sequence[FindingCategory] = _AI_CATEGORIES,
        guideline_count: int,
    ) -> list[CheckOutcome]:
        """Summarise AI coverage separately for each selected category."""

        outcomes: list[CheckOutcome] = []

        for category in categories:
            category_findings = [
                finding
                for finding in ai_findings
                if finding.category == category
            ]

            if any(
                finding.result == FindingResult.CHECK_UNAVAILABLE
                for finding in category_findings
            ):
                status = CheckOutcomeStatus.CHECK_UNAVAILABLE
                message = (
                    f"The AI-assisted {category.value} check could not "
                    "be completed reliably. Review the related findings."
                )

            elif any(
                finding.result == FindingResult.INCONCLUSIVE
                for finding in category_findings
            ):
                status = CheckOutcomeStatus.INCONCLUSIVE
                message = (
                    f"The AI-assisted {category.value} check found "
                    "ambiguous evidence requiring human verification."
                )

            elif any(
                finding.result
                in {
                    FindingResult.CONFLICT,
                    FindingResult.UNSUPPORTED,
                }
                for finding in category_findings
            ):
                status = CheckOutcomeStatus.ISSUES_FOUND
                message = (
                    f"The AI-assisted {category.value} check identified "
                    "one or more potential issues against supplied "
                    "approved guidelines."
                )

            else:
                status = CheckOutcomeStatus.SUPPORTED
                message = (
                    f"The AI-assisted {category.value} check reported "
                    "no issues against the supplied approved guidelines. "
                    "This is advisory and is not a substitute for human review."
                )

            outcomes.append(
                CheckOutcome(
                    category=category,
                    status=status,
                    message=message,
                    detection_method=DetectionMethod.AI_ASSISTED,
                    assessed_count=guideline_count,
                    scope="supplied_approved_guidelines",
                )
            )

        return outcomes

    @staticmethod
    def _build_ai_guidelines(
        rule_versions: Sequence[ApprovedRuleVersionRecord],
        *,
        categories: set[str] | None = None,
    ) -> list[AiGuideline]:
        """Convert loaded, approved rules into AI prompt context.

        When categories is specified, rules belonging to other categories
        are excluded. Only approved records loaded for this organisation
        are eligible for inclusion.
        """

        guidelines: list[AiGuideline] = []

        for rule in rule_versions:
            if (
                categories is not None
                and rule.category not in categories
            ):
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