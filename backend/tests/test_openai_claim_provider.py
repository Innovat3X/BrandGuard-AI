
import json

import pytest

from app.analysis.openai_claim_provider import (
    build_openai_claim_extractor,
    openai_claim_payload_provider,
)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


def test_provider_returns_structured_claims(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    text = "Our product improves efficiency by 40%."
    start = text.index("40%")

    payload = {
        "claims": [
            {
                "fact_key": "efficiency_improvement",
                "claimed_value": "40%",
                "comparison_value": "40%",
                "start_offset": start,
                "end_offset": start + 3,
                "severity": "medium",
            }
        ]
    }

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(payload)
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(
        "app.analysis.openai_claim_provider.httpx.post",
        fake_post,
    )

    result = openai_claim_payload_provider(text)

    assert result == payload["claims"]
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "test-model"
    assert captured["json"]["store"] is False


def test_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        openai_claim_payload_provider("A factual claim.")


def test_provider_rejects_malformed_response(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    monkeypatch.setattr(
        "app.analysis.openai_claim_provider.httpx.post",
        lambda *args, **kwargs: FakeResponse(
            {
                "choices": [
                    {"message": {"content": "not JSON"}}
                ]
            }
        ),
    )

    assert openai_claim_payload_provider("A factual claim.") is None


def test_built_extractor_validates_provider_output(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    text = "Our product improves efficiency by 40%."
    start = text.index("40%")

    payload = {
        "claims": [
            {
                "fact_key": "efficiency_improvement",
                "claimed_value": "40%",
                "comparison_value": "40%",
                "start_offset": start,
                "end_offset": start + 3,
                "severity": "medium",
            }
        ]
    }

    monkeypatch.setattr(
        "app.analysis.openai_claim_provider.httpx.post",
        lambda *args, **kwargs: FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(payload)
                        }
                    }
                ]
            }
        ),
    )

    extractor = build_openai_claim_extractor()
    claims = extractor(text)

    assert claims is not None
    assert len(claims) == 1
    assert claims[0].claimed_value == "40%"
    assert claims[0].source_text == text
