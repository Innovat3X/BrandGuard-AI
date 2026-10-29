
"""Integration tests for AI and deterministic analysis composition."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.analysis.contracts import (
    DetectionMethod,
    Evidence,
    Finding,
    FindingCategory,
    FindingResult,
    Severity,
    TextRangeLocation,
)
from app.infrastructure.db.analysis_knowledge_loader import (
    ApprovedRuleVersionRecord,
)
from app.services.analysis_pipeline_factory import (
    build_database_analysis_pipeline,
)


APPROVED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_context():
    return SimpleNamespace(
        job_id=uuid4(),
        organization_id=uuid4(),
        submission_id=uuid4(),
        submission_version_id=uuid4(),
        content_text="Our cheap product is available today.",
    )


def make_rule(rule_text, organization_id, category="terminology"):
    return ApprovedRuleVersionRecord(
        organization_id=organization_id,
        rule_id=uuid4(),
        version_id=uuid4(),
        version_number=1,
        category=category,
        rule_text=rule_text,
        severity="medium",
        approved_by=uuid4(),
        approved_at=APPROVED_AT,
        effective_from=None,
    )


def make_knowledge(context, rules):
    return SimpleNamespace(
        organization_id=context.organization_id,
        as_of=APPROVED_AT,
        rule_versions=tuple(rules),
        fact_versions=(),
    )


def make_ai_finding(content_text, quote, guideline):
    start = content_text.index(quote)

    return Finding(
        category=FindingCategory.MESSAGING,
        severity=Severity.MEDIUM,
        result=FindingResult.CONFLICT,
        explanation=(
            "The submitted messaging conflicts with an approved "
            "brand guideline."
        ),
        evidence=Evidence(
            submitted_text=quote,
            approved_reference=guideline.rule_text,
            source_name="Approved brand guideline",
        ),
        source_rule_version_id=guideline.version_id,
        location=TextRangeLocation(
            kind="text_range",
            start_offset=start,
            end_offset=start + len(quote),
            matched_text=quote,
        ),
        suggested_correction="Use clear, supportable messaging.",
        detection_method=DetectionMethod.AI_ASSISTED,
        requires_human_review=True,
    )


def make_unavailable_finding(category):
    return Finding(
        category=category,
        severity=Severity.INFO,
        result=FindingResult.CHECK_UNAVAILABLE,
        explanation="The AI provider could not complete this check.",
        evidence=Evidence(source_name="AI brand analysis provider"),
        detection_method=DetectionMethod.AI_ASSISTED,
        requires_human_review=True,
    )


def test_ai_and_deterministic_findings_are_combined():
    context = make_context()
    quote = "Amazing quality guaranteed."
    context.content_text += f" {quote}"

    terminology_rule = make_rule(
        "forbidden_term: cheap",
        context.organization_id,
    )
    messaging_rule = make_rule(
        "Use clear, supportable messaging.",
        context.organization_id,
        category="messaging",
    )
    knowledge = make_knowledge(
        context,
        [terminology_rule, messaging_rule],
    )
    ai_finding = make_ai_finding(
        context.content_text,
        quote,
        messaging_rule,
    )
    settings = SimpleNamespace(ai_provider="openai_compatible")

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
            "OpenAICompatibleBrandAnalysisProvider"
        ) as provider_class,
    ):
        loader_class.return_value.load.return_value = knowledge
        provider_class.return_value.analyze.return_value = [ai_finding]

        pipeline = build_database_analysis_pipeline(
            session=object(),
            claim_extractor=lambda _text: [],
        )
        result = pipeline.analyze(context)

    provider_class.assert_called_once_with(settings)
    provider = provider_class.return_value
    provider.analyze.assert_called_once()

    provider_call = provider.analyze.call_args.kwargs
    assert provider_call["content_text"] == context.content_text

    supplied_guidelines = provider_call["approved_guidelines"]
    guidelines_by_id = {
        guideline.source_rule_version_id: guideline
        for guideline in supplied_guidelines
    }

    assert terminology_rule.version_id in guidelines_by_id
    assert messaging_rule.version_id in guidelines_by_id
    assert (
        guidelines_by_id[messaging_rule.version_id].rule_text
        == messaging_rule.rule_text
    )

    assert result.status == "completed"
    assert result.submission_version_id == context.submission_version_id

    deterministic_findings = [
        finding
        for finding in result.findings
        if finding.detection_method == DetectionMethod.DETERMINISTIC
    ]
    ai_findings = [
        finding
        for finding in result.findings
        if finding.detection_method == DetectionMethod.AI_ASSISTED
    ]

    assert any(
        finding.category == FindingCategory.TERMINOLOGY
        and finding.result == FindingResult.CONFLICT
        and finding.evidence.submitted_text == "cheap"
        for finding in deterministic_findings
    )

    assert len(ai_findings) == 1
    combined_ai_finding = ai_findings[0]

    assert combined_ai_finding.category == FindingCategory.MESSAGING
    assert combined_ai_finding.result == FindingResult.CONFLICT
    assert (
        combined_ai_finding.source_rule_version_id
        == messaging_rule.version_id
    )
    assert (
        combined_ai_finding.evidence.approved_reference
        == messaging_rule.rule_text
    )
    assert combined_ai_finding.location.matched_text == quote

    assert len(result.findings) == 2
    assert result.summary.total == len(result.findings)


def test_unavailable_ai_checks_make_analysis_partial():
    context = make_context()
    terminology_rule = make_rule(
        "forbidden_term: cheap",
        context.organization_id,
    )
    knowledge = make_knowledge(context, [terminology_rule])
    unavailable_findings = [
        make_unavailable_finding(FindingCategory.TONE),
        make_unavailable_finding(FindingCategory.MESSAGING),
    ]
    settings = SimpleNamespace(ai_provider="openai_compatible")

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
            "OpenAICompatibleBrandAnalysisProvider"
        ) as provider_class,
    ):
        loader_class.return_value.load.return_value = knowledge
        provider_class.return_value.analyze.return_value = (
            unavailable_findings
        )

        pipeline = build_database_analysis_pipeline(
            session=object(),
            claim_extractor=lambda _text: [],
        )
        result = pipeline.analyze(context)

    provider_class.return_value.analyze.assert_called_once()

    assert result.status == "partial"

    assert any(
        finding.category == FindingCategory.TERMINOLOGY
        and finding.result == FindingResult.CONFLICT
        for finding in result.findings
    )

    unavailable = [
        finding
        for finding in result.findings
        if finding.result == FindingResult.CHECK_UNAVAILABLE
    ]

    assert {finding.category for finding in unavailable} == {
        FindingCategory.TONE,
        FindingCategory.MESSAGING,
    }
    assert all(
        finding.detection_method == DetectionMethod.AI_ASSISTED
        for finding in unavailable
    )
    assert result.summary.total == len(result.findings)
