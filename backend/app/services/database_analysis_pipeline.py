"""Bridge database-loaded knowledge to the analysis pipeline.

This adapter deliberately does not parse arbitrary rule_text or
fact_text into structured analysis inputs. Explicit, validated
mappers must be supplied for those transformations.
"""

from collections.abc import Callable, Sequence
from typing import Any, Protocol
from uuid import UUID

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
    ) -> Any:
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
    """Load approved knowledge and invoke the configured analysis runner.

    When a structured mapper or claim extractor is absent, the
    corresponding input is marked unavailable. The underlying analysis
    runner must preserve that uncertainty in its response.

    Mapper and extractor exceptions propagate to the worker so its
    existing retry and failure handling remains authoritative.
    """

    def __init__(
        self,
        *,
        knowledge_loader: DatabaseAnalysisKnowledgeLoader,
        analysis_runner: AnalysisRunner,
        rule_mapper: RuleMapper | None = None,
        fact_mapper: FactMapper | None = None,
        claim_extractor: ClaimExtractor | None = None,
    ) -> None:
        self._knowledge_loader = knowledge_loader
        self._analysis_runner = analysis_runner
        self._rule_mapper = rule_mapper
        self._fact_mapper = fact_mapper
        self._claim_extractor = claim_extractor

    def analyze(self, context: AnalysisPipelineContext) -> Any:
        """Run analysis for the exact submission version in the context."""

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

        return self._analysis_runner(
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