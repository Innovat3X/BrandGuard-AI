"""Tests for conservative database knowledge mapping."""

from datetime import datetime, timezone
from uuid import uuid4

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


def make_fact() -> ApprovedFactVersionRecord:
    return ApprovedFactVersionRecord(
        organization_id=uuid4(),
        fact_id=uuid4(),
        version_id=uuid4(),
        version_number=1,
        fact_text="The product is available in three sizes.",
        source_url="https://example.com/product",
        approved_by=uuid4(),
        approved_at=APPROVED_AT,
        effective_from=None,
        expires_at=None,
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

    # The first rule is valid, but the second lacks its required
    # replacement. The complete terminology check must be unavailable.
    assert map_approved_terminology_rules(rules) is None


def test_non_terminology_categories_are_not_parsed_as_terminology():
    rule = make_rule(
        "Always sound confident and professional.",
        category="tone",
    )

    result = map_approved_terminology_rules([rule])

    assert result == ()


def test_empty_terminology_rule_set_returns_empty_tuple():
    assert map_approved_terminology_rules([]) == ()


def test_mapper_preserves_rule_version_identity_and_source_name():
    rule = make_rule(
        "required_term: BrandGuard AI",
        severity="high",
    )

    result = map_approved_terminology_rules([rule])

    assert result is not None
    mapped = result[0]

    assert mapped.source_rule_version_id == rule.version_id
    assert mapped.severity == "high"
    assert mapped.source_name == "Approved terminology rule version 1"


def test_empty_fact_set_is_a_completed_empty_mapping():
    assert map_approved_facts([]) == ()


def test_nonempty_free_text_fact_set_is_unavailable():
    fact = make_fact()

    assert map_approved_facts([fact]) is None