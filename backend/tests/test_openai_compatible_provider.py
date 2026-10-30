
"""Tests for the OpenAI-compatible brand analysis provider."""

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.analysis.contracts import (
    DetectionMethod,
    FindingCategory,
    FindingResult,
    Severity,
)
from app.core.settings import Settings
from app.infrastructure.ai.openai_compatible import (
    ApprovedGuideline,
    OpenAICompatibleBrandAnalysisProvider,
)


CONTENT = "This is the best product in the world."


def make_settings(**overrides) -> Settings:
    """Build isolated settings without requiring a real API key."""
    values = {
        "ai_provider": "openai_compatible",
        "ai_api_key": "test-api-key",
        "ai_base_url": "https://example.test/v1",
        "ai_model": "test-model",
        "ai_timeout_seconds": 5.0,
        "ai_max_output_tokens": 512,
    }
    values.update(overrides)
    return Settings(**values)


def make_guideline() -> ApprovedGuideline:
    return ApprovedGuideline(
        source_rule_version_id=uuid4(),
        category="messaging",
        rule_text="Avoid unsupported superlative claims.",
        severity=Severity.HIGH,
    )


def make_response(findings: list[dict]) -> MagicMock:
    """Mock a successful OpenAI-compatible chat-completions response."""
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({"findings": findings})
                }
            }
        ]
    }
    return response


def assert_unavailable_findings(findings: list) -> None:
    """Both AI check categories must be explicitly unavailable."""
    assert len(findings) == 2
    assert {finding.category for finding in findings} == {
        FindingCategory.TONE,
        FindingCategory.MESSAGING,
    }
    assert all(
        finding.result == FindingResult.CHECK_UNAVAILABLE
        for finding in findings
    )
    assert all(
        finding.detection_method == DetectionMethod.AI_ASSISTED
        for finding in findings
    )
    assert all(finding.requires_human_review for finding in findings)


def test_valid_response_maps_finding_and_exact_quote_location():
    guideline = make_guideline()
    quote = "best product in the world"

    response_data = {
        "category": "messaging",
        "severity": "high",
        "result": "conflict",
        "explanation": "The content makes an unsupported superlative claim.",
        "quote": quote,
        "approved_rule_id": str(guideline.source_rule_version_id),
        "suggested_correction": "A product designed for everyday use.",
    }

    with patch(
        "app.infrastructure.ai.openai_compatible.httpx.post",
        return_value=make_response([response_data]),
    ) as mock_post:
        provider = OpenAICompatibleBrandAnalysisProvider(make_settings())
        findings = provider.analyze(
            content_text=CONTENT,
            approved_guidelines=[guideline],
        )

    assert len(findings) == 1
    finding = findings[0]

    assert finding.category == FindingCategory.MESSAGING
    assert finding.severity == Severity.HIGH
    assert finding.result == FindingResult.CONFLICT
    assert finding.detection_method == DetectionMethod.AI_ASSISTED
    assert finding.requires_human_review is True
    assert finding.source_rule_version_id == guideline.source_rule_version_id
    assert finding.evidence.submitted_text == quote
    assert finding.evidence.approved_reference == guideline.rule_text
    assert finding.location is not None
    assert finding.location.matched_text == quote
    assert finding.location.start_offset == CONTENT.index(quote)
    assert finding.location.end_offset == CONTENT.index(quote) + len(quote)
    assert finding.suggested_correction == (
        "A product designed for everyday use."
    )

    mock_post.assert_called_once()
    args = mock_post.call_args
    assert args.args[0] == (
        "https://example.test/v1/chat/completions"
    )
    assert args.kwargs["headers"]["Authorization"] == (
        "Bearer test-api-key"
    )
    assert args.kwargs["timeout"] == 5.0

    sent_body = args.kwargs["json"]
    assert sent_body["model"] == "test-model"
    assert sent_body["temperature"] == 0
    assert sent_body["stream"] is False

    submitted_data = json.loads(sent_body["messages"][1]["content"])
    assert submitted_data["submitted_content"] == CONTENT
    assert submitted_data["approved_guidelines"][0]["id"] == str(
        guideline.source_rule_version_id
    )


def test_empty_findings_response_returns_empty_list():
    guideline = make_guideline()

    with patch(
        "app.infrastructure.ai.openai_compatible.httpx.post",
        return_value=make_response([]),
    ):
        provider = OpenAICompatibleBrandAnalysisProvider(make_settings())
        findings = provider.analyze(
            content_text=CONTENT,
            approved_guidelines=[guideline],
        )

    assert findings == []


@pytest.mark.parametrize(
    "settings",
    [
        make_settings(ai_provider="disabled"),
        make_settings(ai_api_key=None),
        make_settings(ai_api_key=""),
        make_settings(ai_model=None),
        make_settings(ai_model=""),
    ],
)
def test_unconfigured_provider_fails_closed(settings):
    with patch(
        "app.infrastructure.ai.openai_compatible.httpx.post"
    ) as mock_post:
        provider = OpenAICompatibleBrandAnalysisProvider(settings)
        findings = provider.analyze(
            content_text=CONTENT,
            approved_guidelines=[make_guideline()],
        )

    assert_unavailable_findings(findings)
    mock_post.assert_not_called()


def test_empty_content_returns_unavailable_findings():
    with patch(
        "app.infrastructure.ai.openai_compatible.httpx.post"
    ) as mock_post:
        provider = OpenAICompatibleBrandAnalysisProvider(make_settings())
        findings = provider.analyze(
            content_text="   ",
            approved_guidelines=[make_guideline()],
        )

    assert_unavailable_findings(findings)
    mock_post.assert_not_called()


def test_missing_approved_guidelines_returns_unavailable_findings():
    with patch(
        "app.infrastructure.ai.openai_compatible.httpx.post"
    ) as mock_post:
        provider = OpenAICompatibleBrandAnalysisProvider(make_settings())
        findings = provider.analyze(
            content_text=CONTENT,
            approved_guidelines=[],
        )

    assert_unavailable_findings(findings)
    mock_post.assert_not_called()


def test_provider_timeout_returns_unavailable_findings():
    with patch(
        "app.infrastructure.ai.openai_compatible.httpx.post",
        side_effect=httpx.TimeoutException("request timed out"),
    ):
        provider = OpenAICompatibleBrandAnalysisProvider(make_settings())
        findings = provider.analyze(
            content_text=CONTENT,
            approved_guidelines=[make_guideline()],
        )

    assert_unavailable_findings(findings)


@pytest.mark.parametrize(
    "model_content",
    [
        "not valid JSON",
        '{"unexpected_field": []}',
        '{"findings": [{"category": "visual"}]}',
    ],
)
def test_invalid_model_response_returns_unavailable_findings(
    model_content,
):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"message": {"content": model_content}}]
    }

    with patch(
        "app.infrastructure.ai.openai_compatible.httpx.post",
        return_value=response,
    ):
        provider = OpenAICompatibleBrandAnalysisProvider(make_settings())
        findings = provider.analyze(
            content_text=CONTENT,
            approved_guidelines=[make_guideline()],
        )

    assert_unavailable_findings(findings)


@pytest.mark.parametrize(
    "quote",
    [
        "a quote that is not present",
        "",
    ],
)
def test_invalid_quote_returns_unavailable_findings(quote):
    guideline = make_guideline()
    response_data = {
        "category": "messaging",
        "severity": "high",
        "result": "conflict",
        "explanation": "Potential messaging inconsistency.",
        "quote": quote,
        "approved_rule_id": str(guideline.source_rule_version_id),
        "suggested_correction": None,
    }

    with patch(
        "app.infrastructure.ai.openai_compatible.httpx.post",
        return_value=make_response([response_data]),
    ):
        provider = OpenAICompatibleBrandAnalysisProvider(make_settings())
        findings = provider.analyze(
            content_text=CONTENT,
            approved_guidelines=[guideline],
        )

    assert_unavailable_findings(findings)


def test_unknown_guideline_id_returns_unavailable_findings():
    response_data = {
        "category": "messaging",
        "severity": "high",
        "result": "conflict",
        "explanation": "Potential messaging inconsistency.",
        "quote": "best product in the world",
        "approved_rule_id": str(uuid4()),
        "suggested_correction": None,
    }

    with patch(
        "app.infrastructure.ai.openai_compatible.httpx.post",
        return_value=make_response([response_data]),
    ):
        provider = OpenAICompatibleBrandAnalysisProvider(make_settings())
        findings = provider.analyze(
            content_text=CONTENT,
            approved_guidelines=[make_guideline()],
        )

    assert_unavailable_findings(findings)


def test_duplicate_guideline_ids_return_unavailable_findings():
    guideline = make_guideline()
    duplicate = guideline.model_copy()

    with patch(
        "app.infrastructure.ai.openai_compatible.httpx.post"
    ) as mock_post:
        provider = OpenAICompatibleBrandAnalysisProvider(make_settings())
        findings = provider.analyze(
            content_text=CONTENT,
            approved_guidelines=[guideline, duplicate],
        )

    assert_unavailable_findings(findings)
    mock_post.assert_not_called()


def test_http_error_returns_unavailable_findings():
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error",
        request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
        response=httpx.Response(500),
    )

    with patch(
        "app.infrastructure.ai.openai_compatible.httpx.post",
        return_value=response,
    ):
        provider = OpenAICompatibleBrandAnalysisProvider(make_settings())
        findings = provider.analyze(
            content_text=CONTENT,
            approved_guidelines=[make_guideline()],
        )

    assert_unavailable_findings(findings)


def test_repeated_quote_returns_unavailable_findings():
    """Repeated quoted text must not be assigned an arbitrary offset."""

    content = "Amazing quality. Our product offers Amazing quality."
    quote = "Amazing quality"
    guideline = make_guideline()

    response_data = {
        "category": "messaging",
        "severity": "high",
        "result": "conflict",
        "explanation": (
            "The messaging may conflict with the approved guideline."
        ),
        "quote": quote,
        "approved_rule_id": str(guideline.source_rule_version_id),
        "suggested_correction": None,
    }

    with patch(
        "app.infrastructure.ai.openai_compatible.httpx.post",
        return_value=make_response([response_data]),
    ):
        provider = OpenAICompatibleBrandAnalysisProvider(make_settings())
        findings = provider.analyze(
            content_text=content,
            approved_guidelines=[guideline],
        )

    assert_unavailable_findings(findings)
