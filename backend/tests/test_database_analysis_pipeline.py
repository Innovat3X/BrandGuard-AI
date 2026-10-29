"""Tests for the database-to-analysis pipeline adapter."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
from app.analysis.pipeline import run_analysis

import pytest

from app.services.database_analysis_pipeline import (
    DatabaseAnalysisPipeline,
)


def make_context():
    return SimpleNamespace(
        job_id=uuid4(),
        organization_id=uuid4(),
        submission_id=uuid4(),
        submission_version_id=uuid4(),
        content_text="Use the approved product name.",
    )


def make_knowledge():
    return SimpleNamespace(
        organization_id=uuid4(),
        rule_versions=(SimpleNamespace(rule_text="Rule record"),),
        fact_versions=(SimpleNamespace(fact_text="Fact record"),),
    )


def test_forwards_context_and_mapped_inputs_to_analysis_runner():
    context = make_context()
    knowledge = make_knowledge()
    loader = Mock()
    loader.load.return_value = knowledge

    terminology_rules = [object()]
    claims = [object()]
    approved_facts = [object()]

    rule_mapper = Mock(return_value=terminology_rules)
    fact_mapper = Mock(return_value=approved_facts)
    claim_extractor = Mock(return_value=claims)

    expected_response = object()
    analysis_runner = Mock(return_value=expected_response)

    pipeline = DatabaseAnalysisPipeline(
        knowledge_loader=loader,
        analysis_runner=analysis_runner,
        rule_mapper=rule_mapper,
        fact_mapper=fact_mapper,
        claim_extractor=claim_extractor,
    )

    result = pipeline.analyze(context)

    loader.load.assert_called_once_with(
        organization_id=context.organization_id,
    )
    rule_mapper.assert_called_once_with(knowledge.rule_versions)
    fact_mapper.assert_called_once_with(knowledge.fact_versions)
    claim_extractor.assert_called_once_with(context.content_text)

    analysis_runner.assert_called_once_with(
        job_id=context.job_id,
        submission_id=context.submission_id,
        submission_version_id=context.submission_version_id,
        content_text=context.content_text,
        terminology_rules=terminology_rules,
        claims=claims,
        approved_facts=approved_facts,
        fact_lookup_completed=True,
    )

    assert result is expected_response


def test_missing_mappers_mark_checks_unavailable():
    context = make_context()
    knowledge = make_knowledge()
    loader = Mock()
    loader.load.return_value = knowledge
    analysis_runner = Mock(return_value="analysis-result")

    pipeline = DatabaseAnalysisPipeline(
        knowledge_loader=loader,
        analysis_runner=analysis_runner,
    )

    result = pipeline.analyze(context)

    assert result == "analysis-result"

    analysis_runner.assert_called_once_with(
        job_id=context.job_id,
        submission_id=context.submission_id,
        submission_version_id=context.submission_version_id,
        content_text=context.content_text,
        terminology_rules=None,
        claims=None,
        approved_facts=(),
        fact_lookup_completed=False,
    )


def test_empty_fact_mapping_means_lookup_completed():
    context = make_context()
    loader = Mock()
    loader.load.return_value = make_knowledge()
    analysis_runner = Mock(return_value="analysis-result")

    pipeline = DatabaseAnalysisPipeline(
        knowledge_loader=loader,
        analysis_runner=analysis_runner,
        fact_mapper=Mock(return_value=[]),
    )

    pipeline.analyze(context)

    call_kwargs = analysis_runner.call_args.kwargs

    assert call_kwargs["approved_facts"] == []
    assert call_kwargs["fact_lookup_completed"] is True


def test_none_fact_mapping_means_lookup_not_completed():
    context = make_context()
    loader = Mock()
    loader.load.return_value = make_knowledge()
    analysis_runner = Mock(return_value="analysis-result")

    pipeline = DatabaseAnalysisPipeline(
        knowledge_loader=loader,
        analysis_runner=analysis_runner,
        fact_mapper=Mock(return_value=None),
    )

    pipeline.analyze(context)

    call_kwargs = analysis_runner.call_args.kwargs

    assert call_kwargs["approved_facts"] == ()
    assert call_kwargs["fact_lookup_completed"] is False


def test_loader_failure_propagates():
    context = make_context()
    loader = Mock()
    loader.load.side_effect = RuntimeError("Database unavailable")
    analysis_runner = Mock()

    pipeline = DatabaseAnalysisPipeline(
        knowledge_loader=loader,
        analysis_runner=analysis_runner,
    )

    with pytest.raises(RuntimeError, match="Database unavailable"):
        pipeline.analyze(context)

    analysis_runner.assert_not_called()


def test_mapper_failure_propagates():
    context = make_context()
    loader = Mock()
    loader.load.return_value = make_knowledge()

    rule_mapper = Mock(side_effect=ValueError("Invalid rule mapping"))
    analysis_runner = Mock()

    pipeline = DatabaseAnalysisPipeline(
        knowledge_loader=loader,
        analysis_runner=analysis_runner,
        rule_mapper=rule_mapper,
    )

    with pytest.raises(ValueError, match="Invalid rule mapping"):
        pipeline.analyze(context)

    analysis_runner.assert_not_called()


def test_claim_extractor_can_report_completed_empty_result():
    context = make_context()
    loader = Mock()
    loader.load.return_value = make_knowledge()
    analysis_runner = Mock(return_value="analysis-result")

    pipeline = DatabaseAnalysisPipeline(
        knowledge_loader=loader,
        analysis_runner=analysis_runner,
        claim_extractor=Mock(return_value=[]),
    )

    pipeline.analyze(context)

    call_kwargs = analysis_runner.call_args.kwargs

    assert call_kwargs["claims"] == []
def test_requested_checks_skip_disabled_checks():
    context = make_context()
    context.requested_checks = {
        "tone": False,
        "messaging": False,
        "terminology": False,
        "factual_claim": True,
    }

    knowledge = make_knowledge()
    loader = Mock()
    loader.load.return_value = knowledge

    rule_mapper = Mock(return_value=[])
    fact_mapper = Mock(return_value=[])
    claim_extractor = Mock(return_value=[])

    analysis_runner = Mock(return_value="analysis-result")
    ai_provider = Mock()

    pipeline = DatabaseAnalysisPipeline(
        knowledge_loader=loader,
        analysis_runner=analysis_runner,
        rule_mapper=rule_mapper,
        fact_mapper=fact_mapper,
        claim_extractor=claim_extractor,
        ai_analysis_provider=ai_provider,
    )

    result = pipeline.analyze(context)

    assert result == "analysis-result"

    # Disabled terminology must not invoke its mapper.
    rule_mapper.assert_not_called()

    # The requested factual-claim check must run its required inputs.
    fact_mapper.assert_called_once_with(knowledge.fact_versions)
    claim_extractor.assert_called_once_with(context.content_text)

    call_kwargs = analysis_runner.call_args.kwargs

    assert call_kwargs["terminology_rules"] is None
    assert call_kwargs["claims"] == []
    assert call_kwargs["approved_facts"] == []
    assert call_kwargs["requested_checks"]["factual_claim"] is True
    assert call_kwargs["requested_checks"]["terminology"] is False

    # Neither AI check was requested.
    ai_provider.analyze.assert_not_called()


def test_requested_ai_check_without_provider_is_unavailable():
    context = make_context()
    context.requested_checks = {
        "tone": True,
        "messaging": False,
        "terminology": False,
        "factual_claim": False,
    }

    loader = Mock()
    loader.load.return_value = make_knowledge()

    pipeline = DatabaseAnalysisPipeline(
        knowledge_loader=loader,
        analysis_runner=run_analysis,
    )

    result = pipeline.analyze(context)

    assert result.status == "partial"

    unavailable = [
        finding
        for finding in result.findings
        if finding.result.value == "check_unavailable"
    ]

    assert len(unavailable) == 1
    assert unavailable[0].category.value == "tone"

    # A disabled AI category must not be reported as unavailable.
    assert all(
        finding.category.value != "messaging"
        for finding in result.findings
    )