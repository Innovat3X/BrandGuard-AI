
import json

from app.analysis.claim_extraction import (
    build_claim_extractor,
    validate_claim_payload,
)


def make_payload(text: str) -> list[dict]:
    start = text.index("40%")
    end = start + len("40%")

    return [
        {
            "fact_key": "efficiency_improvement",
            "claimed_value": "40%",
            "comparison_value": "40%",
            "start_offset": start,
            "end_offset": end,
            "severity": "medium",
        }
    ]


def test_valid_claim_preserves_exact_source_text_and_offsets():
    text = "Our product improves efficiency by 40%."

    claims = validate_claim_payload(text, make_payload(text))

    assert claims is not None
    assert len(claims) == 1

    claim = claims[0]
    assert claim.source_text == text
    assert claim.claimed_value == "40%"
    assert text[claim.start_offset:claim.end_offset] == "40%"


def test_json_string_payload_is_supported():
    text = "Our product improves efficiency by 40%."
    payload = json.dumps(make_payload(text))

    claims = validate_claim_payload(text, payload)

    assert claims is not None
    assert len(claims) == 1


def test_empty_list_means_extraction_completed_without_claims():
    assert validate_claim_payload("A welcome message.", []) == []


def test_none_means_extraction_is_unavailable():
    assert (
        validate_claim_payload(
            "Efficiency improves by 40%.",
            None,
        )
        is None
    )


def test_incorrect_source_offsets_are_rejected():
    text = "Our product improves efficiency by 40%."
    payload = make_payload(text)
    payload[0]["start_offset"] = 0

    assert validate_claim_payload(text, payload) is None


def test_malformed_json_is_rejected():
    assert validate_claim_payload("A claim.", "{not valid JSON") is None


def test_unexpected_provider_fields_are_rejected():
    text = "Our product improves efficiency by 40%."
    payload = make_payload(text)
    payload[0]["invented_evidence"] = "Not an approved source"

    assert validate_claim_payload(text, payload) is None


def test_extractor_calls_provider_with_original_text():
    text = "Our product improves efficiency by 40%."
    received = []

    def fake_provider(content: str) -> object:
        received.append(content)
        return make_payload(content)

    extractor = build_claim_extractor(fake_provider)
    claims = extractor(text)

    assert received == [text]
    assert claims is not None
    assert claims[0].source_text == text
