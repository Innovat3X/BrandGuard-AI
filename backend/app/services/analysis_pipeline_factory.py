"""Composition factory for database-backed content analysis."""

from sqlalchemy.orm import Session

from app.analysis.pipeline import run_analysis
from app.infrastructure.db.analysis_knowledge_loader import (
    DatabaseAnalysisKnowledgeLoader,
)
from app.services.analysis_knowledge_mappers import (
    map_approved_facts,
    map_approved_terminology_rules,
)
from app.services.database_analysis_pipeline import (
    AnalysisRunner,
    ClaimExtractor,
    DatabaseAnalysisPipeline,
)


def build_database_analysis_pipeline(
    session: Session,
    *,
    analysis_runner: AnalysisRunner | None = None,
    claim_extractor: ClaimExtractor | None = None,
    rule_limit: int = 100,
    fact_limit: int = 100,
) -> DatabaseAnalysisPipeline:
    """Build a database-backed pipeline using the real analysis runner.

    A custom runner can be injected for tests. Otherwise, the existing
    app.analysis.pipeline.run_analysis function is used.

    Until a claim extractor is supplied, factual-claim extraction is
    reported as unavailable by the analysis runner.

    The current fact schema does not contain structured fact keys or
    canonical comparison values. Non-empty free-text fact sets therefore
    remain unavailable for structured claim verification.
    """

    knowledge_loader = DatabaseAnalysisKnowledgeLoader(
        session,
        rule_limit=rule_limit,
        fact_limit=fact_limit,
    )

    return DatabaseAnalysisPipeline(
        knowledge_loader=knowledge_loader,
        analysis_runner=(
            run_analysis if analysis_runner is None else analysis_runner
        ),
        rule_mapper=map_approved_terminology_rules,
        fact_mapper=map_approved_facts,
        claim_extractor=claim_extractor,
    )