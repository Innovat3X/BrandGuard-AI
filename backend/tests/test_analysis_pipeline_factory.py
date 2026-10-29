"""Tests for the database-backed analysis pipeline factory."""

from unittest.mock import patch

from app.analysis.claim_extraction import extract_structured_claims
from app.services.analysis_knowledge_mappers import (
    map_approved_facts,
    map_approved_terminology_rules,
)
from app.services.analysis_pipeline_factory import (
    build_database_analysis_pipeline,
)


def test_factory_wires_loader_mappers_runner_and_custom_extractor():
    session = object()
    analysis_runner = object()
    claim_extractor = object()

    with (
        patch(
            "app.services.analysis_pipeline_factory."
            "DatabaseAnalysisKnowledgeLoader"
        ) as loader_class,
        patch(
            "app.services.analysis_pipeline_factory."
            "DatabaseAnalysisPipeline"
        ) as pipeline_class,
    ):
        loader_instance = loader_class.return_value
        expected_pipeline = pipeline_class.return_value

        result = build_database_analysis_pipeline(
            session,
            analysis_runner=analysis_runner,
            claim_extractor=claim_extractor,
        )

    loader_class.assert_called_once_with(
        session,
        rule_limit=100,
        fact_limit=100,
    )

    pipeline_class.assert_called_once_with(
        knowledge_loader=loader_instance,
        analysis_runner=analysis_runner,
        rule_mapper=map_approved_terminology_rules,
        fact_mapper=map_approved_facts,
        claim_extractor=claim_extractor,
    )

    assert result is expected_pipeline


def test_factory_forwards_custom_limits():
    session = object()
    analysis_runner = object()

    with (
        patch(
            "app.services.analysis_pipeline_factory."
            "DatabaseAnalysisKnowledgeLoader"
        ) as loader_class,
        patch(
            "app.services.analysis_pipeline_factory."
            "DatabaseAnalysisPipeline"
        ),
    ):
        build_database_analysis_pipeline(
            session,
            analysis_runner=analysis_runner,
            rule_limit=25,
            fact_limit=40,
        )

    loader_class.assert_called_once_with(
        session,
        rule_limit=25,
        fact_limit=40,
    )


def test_factory_uses_default_claim_extractor():
    session = object()
    analysis_runner = object()

    with (
        patch(
            "app.services.analysis_pipeline_factory."
            "DatabaseAnalysisKnowledgeLoader"
        ) as loader_class,
        patch(
            "app.services.analysis_pipeline_factory."
            "DatabaseAnalysisPipeline"
        ) as pipeline_class,
    ):
        build_database_analysis_pipeline(
            session,
            analysis_runner=analysis_runner,
        )

    pipeline_class.assert_called_once_with(
        knowledge_loader=loader_class.return_value,
        analysis_runner=analysis_runner,
        rule_mapper=map_approved_terminology_rules,
        fact_mapper=map_approved_facts,
        claim_extractor=extract_structured_claims,
    )


def test_factory_injects_ai_provider_when_enabled():
    settings = type(
        "SettingsStub",
        (),
        {"ai_provider": "openai_compatible"},
    )()

    session = object()
    analysis_runner = object()

    with (
        patch(
            "app.services.analysis_pipeline_factory.get_settings",
            return_value=settings,
        ),
        patch(
            "app.services.analysis_pipeline_factory."
            "DatabaseAnalysisKnowledgeLoader"
        ) as loader_class,
        patch(
            "app.services.analysis_pipeline_factory."
            "DatabaseAnalysisPipeline"
        ) as pipeline_class,
        patch(
            "app.services.analysis_pipeline_factory."
            "OpenAICompatibleBrandAnalysisProvider"
        ) as ai_provider_class,
    ):
        build_database_analysis_pipeline(
            session,
            analysis_runner=analysis_runner,
        )

    ai_provider_class.assert_called_once_with(settings)

    pipeline_class.assert_called_once_with(
        knowledge_loader=loader_class.return_value,
        analysis_runner=analysis_runner,
        rule_mapper=map_approved_terminology_rules,
        fact_mapper=map_approved_facts,
        claim_extractor=extract_structured_claims,
        ai_analysis_provider=ai_provider_class.return_value,
    )