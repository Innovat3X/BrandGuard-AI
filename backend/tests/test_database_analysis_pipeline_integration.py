
"""Integration tests for the database-backed analysis pipeline."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.analysis.contracts import CheckOutcomeStatus
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


def make_rule(rule_text: str, organization_id):
    return ApprovedRuleVersionRecord(
        organization_id=organization_id,
        rule_id=uuid4(),
        version_id=uuid4(),
        version_number=1,
        category="terminology",
        rule_text=rule_text,
        severity="medium",
        approved_by=uuid4(),
        approved_at=APPROVED_AT,
        effective_from=None,
    )


def test_real_analysis_runner_detects_forbidden_terminology():
    context = make_context()
    rule = make_rule(
        "forbidden_term: cheap",
        context.organization_id,
    )

    knowledge = SimpleNamespace(
        organization_id=context.organization_id,
        as_of=APPROVED_AT,
        rule_versions=(rule,),
        fact_versions=(),
    )

    with patch(
        "app.services.analysis_pipeline_factory."
        "DatabaseAnalysisKnowledgeLoader"
    ) as loader_class:
        loader_class.return_value.load.return_value = knowledge

        pipeline = build_database_analysis_pipeline(
            session=object(),
            claim_extractor=lambda _text: [],
        )

        result = pipeline.analyze(context)

    assert result.job_id == context.job_id
    assert result.submission_id == context.submission_id
    assert result.submission_version_id == context.submission_version_id

    # No structured claims were extracted, and AI is disabled by default.
    # Therefore this analysis has limited coverage and is partial.
    assert result.status == "partial"

    assert any(
        outcome.category.value == "factual_claim"
        and outcome.status == CheckOutcomeStatus.COVERAGE_LIMITED
        for outcome in result.check_outcomes
    )

    assert any(
        outcome.category.value == "tone"
        and outcome.status == CheckOutcomeStatus.DISABLED
        for outcome in result.check_outcomes
    )

    assert any(
        outcome.category.value == "messaging"
        and outcome.status == CheckOutcomeStatus.DISABLED
        for outcome in result.check_outcomes
    )

    assert len(result.findings) == 1

    finding = result.findings[0]
    assert finding.category.value == "terminology"
    assert finding.result.value == "conflict"
    assert finding.severity.value == "medium"
    assert finding.source_rule_version_id == rule.version_id
    assert finding.evidence.submitted_text == "cheap"
    assert finding.location.start_offset == 4
    assert finding.location.end_offset == 9
    assert finding.location.matched_text == "cheap"

    assert result.summary.total == 1


def test_unrecognised_rule_text_produces_partial_analysis():
    context = make_context()
    rule = make_rule(
        "Always use friendly language and avoid exaggerated claims.",
        context.organization_id,
    )

    knowledge = SimpleNamespace(
        organization_id=context.organization_id,
        as_of=APPROVED_AT,
        rule_versions=(rule,),
        fact_versions=(),
    )

    with patch(
        "app.services.analysis_pipeline_factory."
        "DatabaseAnalysisKnowledgeLoader"
    ) as loader_class:
        loader_class.return_value.load.return_value = knowledge

        pipeline = build_database_analysis_pipeline(
            session=object(),
            claim_extractor=lambda _text: [],
        )

        result = pipeline.analyze(context)

    assert result.status == "partial"
    assert result.findings

    unavailable = [
        finding
        for finding in result.findings
        if finding.result.value == "check_unavailable"
    ]

    assert unavailable
    assert any(
        finding.category.value == "terminology"
        for finding in unavailable
    )
    assert result.summary.total == len(result.findings)
