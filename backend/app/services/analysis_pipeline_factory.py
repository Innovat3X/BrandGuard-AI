"""Composition factory for database-backed content analysis."""

from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy.orm import Session

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
    analysis_runner: AnalysisRunner,
    claim_extractor: ClaimExtractor | None = None,
    rule_limit: int = 100,
    fact_limit: int = 100,
) -> DatabaseAnalysisPipeline:
    """Construct the database-backed analysis pipeline.

    The caller supplies the analysis runner. Once the analysis module
    is integrated, its run_analysis function can be passed here.

    Claim extraction remains unavailable unless an explicit extractor
    is supplied. The current database fact schema cannot be mapped
    into structured comparison facts, so fact verification will remain
    unavailable when applicable facts exist.

    Rule parsing follows the interim syntax implemented in
    analysis_knowledge_mappers.py. Do not use that syntax for production
    rules until the team adopts it in the shared contract.
    """

    knowledge_loader = DatabaseAnalysisKnowledgeLoader(
        session,
        rule_limit=rule_limit,
        fact_limit=fact_limit,
    )

    return DatabaseAnalysisPipeline(
        knowledge_loader=knowledge_loader,
        analysis_runner=analysis_runner,
        rule_mapper=map_approved_terminology_rules,
        fact_mapper=map_approved_facts,
        claim_extractor=claim_extractor,
    )