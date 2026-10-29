

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

"""Tests for deterministic claim extraction."""

from app.analysis.claim_extraction import extract_structured_claims


def test_extracts_supported_numeric_claims():
    text = (
        "Price: ₹1,299.00. "
        "Discount up to 15%. "
        "Warranty: 2 years. "
        "Battery life: 10 hours. "
        "Weight: 1.5 kg. "
        "Capacity: 750 ml."
    )

    claims = extract_structured_claims(text)

    assert len(claims) == 6

    by_key = {claim.fact_key: claim for claim in claims}

    assert by_key["product_price"].comparison_value == "INR 1299"
    assert by_key["discount_percentage"].comparison_value == "15 %"
    assert by_key["warranty_duration"].comparison_value == "2 years"
    assert by_key["battery_life_duration"].comparison_value == "10 hours"
    assert by_key["product_weight"].comparison_value == "1.5 kg"
    assert by_key["product_capacity"].comparison_value == "750 ml"


def test_claim_locations_match_exact_source_text():
    text = "Our product price is ₹999 today."

    claims = extract_structured_claims(text)

    assert len(claims) == 1

    claim = claims[0]

    assert claim.claimed_value == "₹999"
    assert text[claim.start_offset:claim.end_offset] == claim.claimed_value
    assert claim.source_text == text


def test_normalises_currency_and_number_format():
    text = "Price: INR 1,299.00"

    claims = extract_structured_claims(text)

    assert len(claims) == 1
    assert claims[0].fact_key == "product_price"
    assert claims[0].comparison_value == "INR 1299"


def test_ignores_price_without_explicit_currency():
    text = "The product price is 999."

    claims = extract_structured_claims(text)

    assert claims == ()


def test_ignores_unsupported_natural_language_claims():
    text = (
        "Our product is the best in the market. "
        "Customers absolutely love it."
    )

    claims = extract_structured_claims(text)

    assert claims == ()


def test_preserves_multiple_claims_in_source_order():
    text = "Price: ₹999. Warranty: 2 years."

    claims = extract_structured_claims(text)

    assert len(claims) == 2
    assert [claim.fact_key for claim in claims] == [
        "product_price",
        "warranty_duration",
    ]

    assert claims[0].start_offset < claims[1].start_offset


def test_returns_empty_tuple_when_no_supported_claims_exist():
    claims = extract_structured_claims(
        "Welcome to our product page."
    )

    assert claims == ()


def test_does_not_change_original_submitted_text():
    text = "Price: ₹1,299.00 and warranty: 2 years."

    claims = extract_structured_claims(text)

    assert claims
    assert all(claim.source_text == text for claim in claims)

    for claim in claims:
        assert (
            text[claim.start_offset:claim.end_offset]
            == claim.claimed_value
        )

