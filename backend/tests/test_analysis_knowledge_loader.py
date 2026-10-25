"""Tests for organisation-scoped approved knowledge loading."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.infrastructure.db.analysis_knowledge_loader import (
    DatabaseAnalysisKnowledgeLoader,
    IncompleteApprovedKnowledgeError,
)


AS_OF = datetime(2026, 6, 1, tzinfo=timezone.utc)
APPROVED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
_UNSET = object()


def make_rule(
    organization_id,
    *,
    status="approved",
    approved_by=_UNSET,
    approved_at=APPROVED_AT,
):
    if approved_by is _UNSET:
        approved_by = uuid4()

    return SimpleNamespace(
        organization_id=organization_id,
        id=uuid4(),
        rule_id=uuid4(),
        version_number=1,
        category="terminology",
        rule_text="Use the approved product name",
        severity="medium",
        status=status,
        approved_by=approved_by,
        approved_at=approved_at,
        effective_from=None,
    )


def make_fact(
    organization_id,
    *,
    status="approved",
    approved_by=_UNSET,
    approved_at=APPROVED_AT,
):
    if approved_by is _UNSET:
        approved_by = uuid4()

    return SimpleNamespace(
        organization_id=organization_id,
        id=uuid4(),
        fact_id=uuid4(),
        version_number=2,
        fact_text="The product is available in three sizes.",
        source_url="https://example.com/product",
        status=status,
        approved_by=approved_by,
        approved_at=approved_at,
        effective_from=None,
        expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def repositories():
    with (
        patch(
            "app.infrastructure.db.analysis_knowledge_loader."
            "BrandRuleRepository"
        ) as rule_repository_class,
        patch(
            "app.infrastructure.db.analysis_knowledge_loader."
            "BrandFactRepository"
        ) as fact_repository_class,
    ):
        rule_repository = rule_repository_class.return_value
        fact_repository = fact_repository_class.return_value

        rule_repository.list_active_rule_versions.return_value = []
        fact_repository.list_active_fact_versions.return_value = []

        yield rule_repository, fact_repository


def test_loads_approved_rules_and_facts_for_organization(repositories):
    organization_id = uuid4()
    rule = make_rule(organization_id)
    fact = make_fact(organization_id)

    rule_repository, fact_repository = repositories
    rule_repository.list_active_rule_versions.return_value = [rule]
    fact_repository.list_active_fact_versions.return_value = [fact]

    loader = DatabaseAnalysisKnowledgeLoader(
        session=object(),
        rule_limit=10,
        fact_limit=10,
    )

    result = loader.load(
        organization_id=organization_id,
        as_of=AS_OF,
    )

    assert result.organization_id == organization_id
    assert result.as_of == AS_OF
    assert len(result.rule_versions) == 1
    assert len(result.fact_versions) == 1

    loaded_rule = result.rule_versions[0]
    assert loaded_rule.organization_id == organization_id
    assert loaded_rule.rule_id == rule.rule_id
    assert loaded_rule.version_id == rule.id
    assert loaded_rule.version_number == 1
    assert loaded_rule.rule_text == rule.rule_text
    assert loaded_rule.approved_by == rule.approved_by
    assert loaded_rule.approved_at == rule.approved_at

    loaded_fact = result.fact_versions[0]
    assert loaded_fact.organization_id == organization_id
    assert loaded_fact.fact_id == fact.fact_id
    assert loaded_fact.version_id == fact.id
    assert loaded_fact.version_number == 2
    assert loaded_fact.fact_text == fact.fact_text
    assert loaded_fact.source_url == fact.source_url
    assert loaded_fact.approved_by == fact.approved_by
    assert loaded_fact.approved_at == fact.approved_at

    rule_repository.list_active_rule_versions.assert_called_once_with(
        organization_id=organization_id,
        as_of=AS_OF,
        limit=10,
    )
    fact_repository.list_active_fact_versions.assert_called_once_with(
        organization_id=organization_id,
        as_of=AS_OF,
        limit=10,
    )


def test_rejects_naive_as_of_timestamp(repositories):
    loader = DatabaseAnalysisKnowledgeLoader(
        session=object(),
        rule_limit=10,
        fact_limit=10,
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        loader.load(
            organization_id=uuid4(),
            as_of=datetime(2026, 6, 1),
        )


def test_rejects_rule_from_another_organization(repositories):
    organization_id = uuid4()
    rule = make_rule(uuid4())

    rule_repository, _ = repositories
    rule_repository.list_active_rule_versions.return_value = [rule]

    loader = DatabaseAnalysisKnowledgeLoader(
        session=object(),
        rule_limit=10,
        fact_limit=10,
    )

    with pytest.raises(
        IncompleteApprovedKnowledgeError,
        match="outside the requested organisation scope",
    ):
        loader.load(
            organization_id=organization_id,
            as_of=AS_OF,
        )


def test_rejects_fact_from_another_organization(repositories):
    organization_id = uuid4()
    fact = make_fact(uuid4())

    _, fact_repository = repositories
    fact_repository.list_active_fact_versions.return_value = [fact]

    loader = DatabaseAnalysisKnowledgeLoader(
        session=object(),
        rule_limit=10,
        fact_limit=10,
    )

    with pytest.raises(
        IncompleteApprovedKnowledgeError,
        match="outside the requested organisation scope",
    ):
        loader.load(
            organization_id=organization_id,
            as_of=AS_OF,
        )


@pytest.mark.parametrize(
    ("status", "approved_by", "approved_at"),
    [
        ("draft", uuid4(), APPROVED_AT),
        ("archived", uuid4(), APPROVED_AT),
        ("approved", None, APPROVED_AT),
        ("approved", uuid4(), None),
    ],
)
def test_rejects_rule_without_valid_approval_metadata(
    repositories,
    status,
    approved_by,
    approved_at,
):
    organization_id = uuid4()
    rule = make_rule(
        organization_id,
        status=status,
        approved_by=approved_by,
        approved_at=approved_at,
    )

    rule_repository, _ = repositories
    rule_repository.list_active_rule_versions.return_value = [rule]

    loader = DatabaseAnalysisKnowledgeLoader(
        session=object(),
        rule_limit=10,
        fact_limit=10,
    )

    with pytest.raises(
        IncompleteApprovedKnowledgeError,
        match="invalid approval metadata",
    ):
        loader.load(
            organization_id=organization_id,
            as_of=AS_OF,
        )


def test_rejects_possible_rule_truncation(repositories):
    organization_id = uuid4()
    rule = make_rule(organization_id)

    rule_repository, _ = repositories
    rule_repository.list_active_rule_versions.return_value = [rule]

    loader = DatabaseAnalysisKnowledgeLoader(
        session=object(),
        rule_limit=1,
        fact_limit=10,
    )

    with pytest.raises(
        IncompleteApprovedKnowledgeError,
        match="reached the configured limit",
    ):
        loader.load(
            organization_id=organization_id,
            as_of=AS_OF,
        )


def test_rejects_expired_fact_returned_as_active(repositories):
    organization_id = uuid4()
    fact = make_fact(organization_id)
    fact.expires_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    _, fact_repository = repositories
    fact_repository.list_active_fact_versions.return_value = [fact]

    loader = DatabaseAnalysisKnowledgeLoader(
        session=object(),
        rule_limit=10,
        fact_limit=10,
    )

    with pytest.raises(
        IncompleteApprovedKnowledgeError,
        match="expired fact version",
    ):
        loader.load(
            organization_id=organization_id,
            as_of=AS_OF,
        )