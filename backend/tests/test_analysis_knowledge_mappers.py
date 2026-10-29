"""Tests for conservative database knowledge mapping."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.infrastructure.db.analysis_knowledge_loader import (
    ApprovedFactVersionRecord,
    ApprovedRuleVersionRecord,
)
from app.services.analysis_knowledge_mappers import (
    map_approved_facts,
    map_approved_terminology_rules,
)


APPROVED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_rule(
    rule_text: str,
    *,
    category: str = "terminology",
    severity: str = "medium",
) -> ApprovedRuleVersionRecord:
    return ApprovedRuleVersionRecord(
        organization_id=uuid4(),
        rule_id=uuid4(),
        version_id=uuid4(),
        version_number=1,
        category=category,
        rule_text=rule_text,
        severity=severity,
        approved_by=uuid4(),
        approved_at=APPROVED_AT,
        effective_from=None,
    )


def make_fact(
    *,
    fact_key: str | None = None,
    structured_value: dict | None = None,
    fact_text: str = "Approved product information.",
) -> ApprovedFactVersionRecord:
    return ApprovedFactVersionRecord(
        organization_id=uuid4(),
        fact_id=uuid4(),
        version_id=uuid4(),
        version_number=1,
        fact_text=fact_text,
        source_url="https://example.com/product",
        approved_by=uuid4(),
        approved_at=APPROVED_AT,
        effective_from=None,
        expires_at=None,
        fact_key=fact_key,
        structured_value=structured_value,
    )


def test_maps_forbidden_term_without_replacement():
    rule = make_rule("forbidden_term: cheap")

    result = map_approved_terminology_rules([rule])

    assert result is not None
    assert len(result) == 1

    mapped = result[0]
    assert mapped.source_rule_version_id == rule.version_id
    assert mapped.rule_type == "forbidden_term"
    assert mapped.term == "cheap"
    assert mapped.severity == "medium"
    assert mapped.status == "approved"
    assert mapped.replacement is None


def test_maps_forbidden_term_with_replacement():
    result = map_approved_terminology_rules(
        [make_rule("forbidden_term: cheap -> affordable")]
    )

    assert result is not None
    assert len(result) == 1
    assert result[0].rule_type == "forbidden_term"
    assert result[0].term == "cheap"
    assert result[0].replacement == "affordable"


def test_maps_required_term():
    result = map_approved_terminology_rules(
        [make_rule("required_term: BrandGuard AI")]
    )

    assert result is not None
    assert len(result) == 1
    assert result[0].rule_type == "required_term"
    assert result[0].term == "BrandGuard AI"
    assert result[0].replacement is None


def test_maps_preferred_term_with_replacement():
    result = map_approved_terminology_rules(
        [make_rule("preferred_term: old name -> new name")]
    )

    assert result is not None
    assert len(result) == 1
    assert result[0].rule_type == "preferred_term"
    assert result[0].term == "old name"
    assert result[0].replacement == "new name"


def test_unrecognised_terminology_prose_returns_unavailable():
    rule = make_rule(
        "Always use friendly language and avoid exaggerated claims."
    )

    assert map_approved_terminology_rules([rule]) is None


def test_invalid_terminology_syntax_is_not_partially_mapped():
    rules = [
        make_rule("forbidden_term: cheap"),
        make_rule("preferred_term: old name"),
    ]

    assert map_approved_terminology_rules(rules) is None


def test_non_terminology_categories_are_not_parsed_as_terminology():
    rule = make_rule(
        "Always sound confident and professional.",
        category="tone",
    )

    assert map_approved_terminology_rules([rule]) == ()


def test_empty_terminology_rule_set_returns_empty_tuple():
    assert map_approved_terminology_rules([]) == ()


def test_mapper_preserves_rule_version_identity_and_source_name():
    rule = make_rule(
        "required_term: BrandGuard AI",
        severity="high",
    )

    result = map_approved_terminology_rules([rule])

    assert result is not None
    assert result[0].source_rule_version_id == rule.version_id
    assert result[0].severity == "high"
    assert result[0].source_name == "Approved terminology rule version 1"


def test_empty_fact_set_is_a_completed_empty_mapping():
    assert map_approved_facts([]) == ()


def test_legacy_free_text_fact_returns_unavailable():
    assert map_approved_facts([make_fact()]) is None


@pytest.mark.parametrize(
    ("fact_key", "structured_value", "expected_display", "expected_comparison"),
    [
        (
            "product_price",
            {"kind": "currency", "value": "1299", "unit": "INR"},
            "₹1299",
            "INR 1299",
        ),
        (
            "discount_percentage",
            {"kind": "percentage", "value": "15", "unit": "%"},
            "15%",
            "15 %",
        ),
        (
            "warranty_duration",
            {"kind": "duration", "value": "2", "unit": "years"},
            "2 years",
            "2 years",
        ),
        (
            "battery_life_duration",
            {"kind": "duration", "value": "10", "unit": "hours"},
            "10 hours",
            "10 hours",
        ),
        (
            "product_weight",
            {"kind": "quantity", "value": "1.50", "unit": "kg"},
            "1.5 kg",
            "1.5 kg",
        ),
        (
            "product_capacity",
            {"kind": "quantity", "value": "750", "unit": "ml"},
            "750 ml",
            "750 ml",
        ),
    ],
)
def test_maps_supported_structured_facts(
    fact_key,
    structured_value,
    expected_display,
    expected_comparison,
):
    record = make_fact(
        fact_key=fact_key,
        structured_value=structured_value,
    )

    result = map_approved_facts([record])

    assert result is not None
    assert len(result) == 1

    mapped = result[0]
    assert mapped.source_fact_version_id == record.version_id
    assert mapped.fact_key == fact_key
    assert mapped.approved_value == expected_display
    assert mapped.comparison_value == expected_comparison
    assert mapped.status == "approved"
    assert mapped.source_url == record.source_url


@pytest.mark.parametrize(
    ("fact_key", "structured_value"),
    [
        (
            "product_price",
            {"kind": "quantity", "value": "999", "unit": "INR"},
        ),
        (
            "product_price",
            {"kind": "currency", "value": "999", "unit": "JPY"},
        ),
        (
            "product_weight",
            {"kind": "quantity", "value": "1", "unit": "litres"},
        ),
        (
            "product_capacity",
            {"kind": "quantity", "value": "-2", "unit": "ml"},
        ),
        (
            "product_capacity",
            {"kind": "quantity", "value": "unknown", "unit": "ml"},
        ),
        (
            "unknown_key",
            {"kind": "quantity", "value": "1", "unit": "kg"},
        ),
        (
            "product_price",
            {"kind": "currency", "value": "1299"},
        ),
    ],
)
def test_invalid_structured_fact_returns_unavailable(
    fact_key,
    structured_value,
):
    assert map_approved_facts(
        [
            make_fact(
                fact_key=fact_key,
                structured_value=structured_value,
            )
        ]
    ) is None


def test_mixed_structured_and_legacy_facts_return_unavailable():
    records = [
        make_fact(
            fact_key="product_price",
            structured_value={
                "kind": "currency",
                "value": "1299",
                "unit": "INR",
            },
        ),
        make_fact(),
    ]

    assert map_approved_facts(records) is None


def test_fact_mapping_preserves_source_version_id():
    record = make_fact(
        fact_key="product_weight",
        structured_value={
            "kind": "quantity",
            "value": "2",
            "unit": "kg",
        },
    )

    result = map_approved_facts([record])

    assert result is not None
    assert result[0].source_fact_version_id == record.version_id
    assert result[0].fact_text == record.fact_text