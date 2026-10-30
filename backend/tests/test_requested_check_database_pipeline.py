from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.analysis.contracts import (
    DetectionMethod,
    Evidence,
    Finding,
    FindingCategory,
    FindingResult,
    Severity,
)
from app.analysis.pipeline import build_analysis_response
from app.services.database_analysis_pipeline import (
    DatabaseAnalysisPipeline,
)


def make_context(requested_checks):
    return SimpleNamespace(
        job_id=uuid4(),
        organization_id=uuid4(),
        submission_id=uuid4(),
        submission_version_id=uuid4(),
        content_text="Our product is excellent.",
        requested_checks=requested_checks,
    )


def make_knowledge():
    return SimpleNamespace(
        organization_id=uuid4(),
        rule_versions=(),
        fact_versions=(),
    )


def make_rule(category):
    return SimpleNamespace(
        version_id=uuid4(),
        category=category,
        rule_text=f"Approved {category} guideline.",
        severity="medium",
    )


def make_response(context, status="completed"):
    return build_analysis_response(
        job_id=context.job_id,
        submission_id=context.submission_id,
        submission_version_id=context.submission_version_id,
        findings=[],
        status=status,
    )


def make_ai_finding(category):
    return Finding(
        category=FindingCategory(category),
        severity=Severity.MEDIUM,
        result=FindingResult.CONFLICT,
        explanation=f"An AI-assisted {category} issue was detected.",
        evidence=Evidence(
            submitted_text="Our product is excellent.",
            source_name="AI analysis provider",
        ),
        detection_method=DetectionMethod.AI_ASSISTED,
        requires_human_review=True,
    )


def make_pipeline(
    context,
    *,
    knowledge=None,
    analysis_runner=None,
    rule_mapper=None,
    fact_mapper=None,
    claim_extractor=None,
    ai_provider=None,
):
    loader = Mock()
    loader.load.return_value = knowledge or make_knowledge()

    runner = analysis_runner or Mock(
        return_value=make_response(context)
    )

    pipeline = DatabaseAnalysisPipeline(
        knowledge_loader=loader,
        analysis_runner=runner,
        rule_mapper=rule_mapper,
        fact_mapper=fact_mapper,
        claim_extractor=claim_extractor,
        ai_analysis_provider=ai_provider,
    )

    return pipeline, loader, runner


def test_explicit_terminology_selection_skips_factual_mappers():
    context = make_context(
        {
            "tone": False,
            "messaging": False,
            "terminology": True,
            "factual_claim": False,
        }
    )

    terminology_rules = [object()]
    rule_mapper = Mock(return_value=terminology_rules)
    fact_mapper = Mock(return_value=[])
    claim_extractor = Mock(return_value=[])

    pipeline, loader, runner = make_pipeline(
        context,
        rule_mapper=rule_mapper,
        fact_mapper=fact_mapper,
        claim_extractor=claim_extractor,
    )

    pipeline.analyze(context)

    loader.load.assert_called_once_with(
        organization_id=context.organization_id
    )
    rule_mapper.assert_called_once()
    fact_mapper.assert_not_called()
    claim_extractor.assert_not_called()

    kwargs = runner.call_args.kwargs

    assert kwargs["terminology_rules"] == terminology_rules
    assert kwargs["claims"] is None
    assert kwargs["approved_facts"] == ()
    assert kwargs["fact_lookup_completed"] is False
    assert kwargs["requested_checks"] == {
        "tone": False,
        "messaging": False,
        "terminology": True,
        "factual_claim": False,
    }


def test_explicit_factual_claim_selection_skips_terminology_mapper():
    context = make_context(
        {
            "tone": False,
            "messaging": False,
            "terminology": False,
            "factual_claim": True,
        }
    )

    claims = [object()]
    approved_facts = [object()]

    rule_mapper = Mock()
    fact_mapper = Mock(return_value=approved_facts)
    claim_extractor = Mock(return_value=claims)

    pipeline, _, runner = make_pipeline(
        context,
        rule_mapper=rule_mapper,
        fact_mapper=fact_mapper,
        claim_extractor=claim_extractor,
    )

    pipeline.analyze(context)

    rule_mapper.assert_not_called()
    fact_mapper.assert_called_once()
    claim_extractor.assert_called_once_with(context.content_text)

    kwargs = runner.call_args.kwargs

    assert kwargs["terminology_rules"] is None
    assert kwargs["claims"] == claims
    assert kwargs["approved_facts"] == approved_facts
    assert kwargs["fact_lookup_completed"] is True


def test_empty_fact_mapping_still_means_lookup_completed():
    context = make_context(
        {
            "tone": False,
            "messaging": False,
            "terminology": False,
            "factual_claim": True,
        }
    )

    fact_mapper = Mock(return_value=[])
    claim_extractor = Mock(return_value=[])

    pipeline, _, runner = make_pipeline(
        context,
        fact_mapper=fact_mapper,
        claim_extractor=claim_extractor,
    )

    pipeline.analyze(context)

    kwargs = runner.call_args.kwargs

    assert kwargs["approved_facts"] == []
    assert kwargs["claims"] == []
    assert kwargs["fact_lookup_completed"] is True


def test_selected_ai_check_without_provider_is_unavailable():
    context = make_context(
        {
            "tone": True,
            "messaging": False,
            "terminology": False,
            "factual_claim": False,
        }
    )

    pipeline, _, _ = make_pipeline(context)

    result = pipeline.analyze(context)

    tone_findings = [
        finding
        for finding in result.findings
        if finding.category == FindingCategory.TONE
    ]

    assert len(tone_findings) == 1
    assert tone_findings[0].result == FindingResult.CHECK_UNAVAILABLE

    tone_outcome = next(
        outcome
        for outcome in result.check_outcomes
        if outcome.category == FindingCategory.TONE
    )

    assert tone_outcome.status.value == "check_unavailable"
    assert result.status == "partial"


def test_unselected_ai_check_is_disabled_not_unavailable():
    context = make_context(
        {
            "tone": True,
            "messaging": False,
            "terminology": False,
            "factual_claim": False,
        }
    )

    pipeline, _, _ = make_pipeline(context)

    result = pipeline.analyze(context)

    messaging_outcome = next(
        outcome
        for outcome in result.check_outcomes
        if outcome.category == FindingCategory.MESSAGING
    )

    assert messaging_outcome.status.value == "disabled"
    assert messaging_outcome.scope == "not_requested"

    assert not any(
        finding.category == FindingCategory.MESSAGING
        for finding in result.findings
    )


def test_unselected_ai_categories_do_not_call_provider():
    context = make_context(
        {
            "tone": False,
            "messaging": False,
            "terminology": True,
            "factual_claim": False,
        }
    )

    provider = Mock()

    pipeline, _, _ = make_pipeline(
        context,
        ai_provider=provider,
    )

    pipeline.analyze(context)

    provider.analyze.assert_not_called()


def test_ai_provider_receives_only_selected_category_guidelines():
    context = make_context(
        {
            "tone": True,
            "messaging": False,
            "terminology": False,
            "factual_claim": False,
        }
    )

    knowledge = make_knowledge()
    knowledge.rule_versions = (
        make_rule("tone"),
        make_rule("messaging"),
    )

    provider = Mock()
    provider.analyze.return_value = [
        make_ai_finding("tone"),
        make_ai_finding("messaging"),
    ]

    pipeline, _, _ = make_pipeline(
        context,
        knowledge=knowledge,
        ai_provider=provider,
    )

    result = pipeline.analyze(context)

    provider.analyze.assert_called_once()

    supplied_guidelines = (
        provider.analyze.call_args.kwargs["approved_guidelines"]
    )

    assert [guideline.category for guideline in supplied_guidelines] == [
        "tone"
    ]

    assert any(
        finding.category == FindingCategory.TONE
        for finding in result.findings
    )

    assert not any(
        finding.category == FindingCategory.MESSAGING
        for finding in result.findings
    )


def test_selected_ai_provider_findings_require_human_review():
    context = make_context(
        {
            "tone": True,
            "messaging": False,
            "terminology": False,
            "factual_claim": False,
        }
    )

    knowledge = make_knowledge()
    knowledge.rule_versions = (make_rule("tone"),)

    provider = Mock()
    provider.analyze.return_value = [make_ai_finding("tone")]

    pipeline, _, _ = make_pipeline(
        context,
        knowledge=knowledge,
        ai_provider=provider,
    )

    result = pipeline.analyze(context)

    tone_finding = next(
        finding
        for finding in result.findings
        if finding.category == FindingCategory.TONE
    )

    assert tone_finding.requires_human_review is True
    assert tone_finding.detection_method == DetectionMethod.AI_ASSISTED


def test_legacy_list_selection_is_supported():
    context = make_context(["factual_claim"])

    fact_mapper = Mock(return_value=[])
    claim_extractor = Mock(return_value=[])

    pipeline, _, runner = make_pipeline(
        context,
        rule_mapper=Mock(),
        fact_mapper=fact_mapper,
        claim_extractor=claim_extractor,
    )

    pipeline.analyze(context)

    runner_kwargs = runner.call_args.kwargs

    assert runner_kwargs["requested_checks"] == {
        "tone": False,
        "messaging": False,
        "terminology": False,
        "factual_claim": True,
    }

    assert runner_kwargs["terminology_rules"] is None
    assert fact_mapper.called
    assert claim_extractor.called