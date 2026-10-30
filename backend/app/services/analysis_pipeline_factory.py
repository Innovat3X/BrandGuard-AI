"""Composition factory for database-backed content analysis."""

from sqlalchemy.orm import Session

from app.analysis.claim_extraction import extract_structured_claims
from app.analysis.pipeline import run_analysis
from app.core.settings import get_settings
from app.infrastructure.ai.openai_compatible import (
    OpenAICompatibleBrandAnalysisProvider,
)
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
    """Build the analysis pipeline with optional real AI integration."""

    settings = get_settings()

    knowledge_loader = DatabaseAnalysisKnowledgeLoader(
        session,
        rule_limit=rule_limit,
        fact_limit=fact_limit,
    )

    pipeline_kwargs = {
        "knowledge_loader": knowledge_loader,
        "analysis_runner": (
            run_analysis if analysis_runner is None else analysis_runner
        ),
        "rule_mapper": map_approved_terminology_rules,
        "fact_mapper": map_approved_facts,
        "claim_extractor": (
            extract_structured_claims
            if claim_extractor is None
            else claim_extractor
        ),
    }

    # Preserve deterministic-only behavior unless AI is explicitly enabled.
    if settings.ai_provider == "openai_compatible":
        pipeline_kwargs["ai_analysis_provider"] = (
            OpenAICompatibleBrandAnalysisProvider(settings)
        )

    return DatabaseAnalysisPipeline(**pipeline_kwargs)