"""Bridge approved database knowledge to the content-analysis pipeline."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.analysis.contracts import (
    AnalysisResponse,
    Finding,
    FindingResult,
    Severity,
    build_summary,
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


class DatabaseAnalysisPipeline:
    """Load approved knowledge and run deterministic and optional AI checks."""

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
        """Analyse the exact submission version using approved organisation data."""

        knowledge = self._knowledge_loader.load(
            organization_id=context.organization_id,
        )

        terminology_rules = (
            self._rule_mapper(knowledge.rule_versions)
            if self._rule_mapper is not None
            else None
        )

        claims = (
            self._claim_extractor(context.content_text)
            if self._claim_extractor is not None
            else None
        )

        mapped_facts = (
            self._fact_mapper(knowledge.fact_versions)
            if self._fact_mapper is not None
            else None
        )

        deterministic_result = self._analysis_runner(
            job_id=context.job_id,
            submission_id=context.submission_id,
            submission_version_id=context.submission_version_id,
            content_text=context.content_text,
            terminology_rules=terminology_rules,
            claims=claims,
            approved_facts=(
                mapped_facts if mapped_facts is not None else ()
            ),
            fact_lookup_completed=mapped_facts is not None,
        )

        # Keep existing behavior unchanged unless a provider is explicitly
        # configured and injected by the composition factory.
        if self._ai_analysis_provider is None:
            return deterministic_result

        approved_guidelines = self._build_ai_guidelines(
            knowledge.rule_versions
        )

        ai_findings = self._ai_analysis_provider.analyze(
            content_text=context.content_text,
            approved_guidelines=approved_guidelines,
        )

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
    def _build_ai_guidelines(
        rule_versions: Sequence[ApprovedRuleVersionRecord],
    ) -> list[AiGuideline]:
        """Convert only loaded, approved rules into AI prompt context."""

        guidelines: list[AiGuideline] = []

        for rule in rule_versions:
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