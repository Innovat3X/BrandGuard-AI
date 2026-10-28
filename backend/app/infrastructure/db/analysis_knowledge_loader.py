"""Load approved, currently applicable brand knowledge for analysis."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.repositories.brand_fact_repository import (
    BrandFactRepository,
)
from app.infrastructure.db.repositories.brand_rule_repository import (
    BrandRuleRepository,
)


class IncompleteApprovedKnowledgeError(RuntimeError):
    """Raised when approved knowledge cannot be trusted as complete."""


@dataclass(frozen=True)
class ApprovedRuleVersionRecord:
    """Immutable snapshot of an approved rule version."""

    organization_id: UUID
    rule_id: UUID
    version_id: UUID
    version_number: int
    category: str
    rule_text: str
    severity: str
    approved_by: UUID
    approved_at: datetime
    effective_from: datetime | None


@dataclass(frozen=True)
class ApprovedFactVersionRecord:
    """Immutable snapshot of an approved fact version."""

    organization_id: UUID
    fact_id: UUID
    version_id: UUID
    version_number: int
    fact_text: str
    source_url: str | None
    approved_by: UUID
    approved_at: datetime
    effective_from: datetime | None
    expires_at: datetime | None
    fact_key: str | None = None
    structured_value: dict[str, Any] | None = None


@dataclass(frozen=True)
class LoadedApprovedKnowledge:
    """Approved knowledge retrieved for one organisation and timestamp."""

    organization_id: UUID
    as_of: datetime
    rule_versions: tuple[ApprovedRuleVersionRecord, ...]
    fact_versions: tuple[ApprovedFactVersionRecord, ...]


class DatabaseAnalysisKnowledgeLoader:
    """Retrieve active, approved rules and facts within one organisation."""

    def __init__(
        self,
        session: Session,
        *,
        rule_limit: int = 100,
        fact_limit: int = 100,
    ) -> None:
        if rule_limit < 1:
            raise ValueError("rule_limit must be at least 1.")

        if fact_limit < 1:
            raise ValueError("fact_limit must be at least 1.")

        self._rule_repository = BrandRuleRepository(session)
        self._fact_repository = BrandFactRepository(session)
        self._rule_limit = rule_limit
        self._fact_limit = fact_limit

    def load(
        self,
        *,
        organization_id: UUID,
        as_of: datetime | None = None,
    ) -> LoadedApprovedKnowledge:
        """Load applicable approved versions in the requested organisation."""

        effective_at = as_of or datetime.now(timezone.utc)

        if (
            effective_at.tzinfo is None
            or effective_at.utcoffset() is None
        ):
            raise ValueError("as_of must be timezone-aware.")

        rules = self._rule_repository.list_active_rule_versions(
            organization_id=organization_id,
            as_of=effective_at,
            limit=self._rule_limit,
        )

        facts = self._fact_repository.list_active_fact_versions(
            organization_id=organization_id,
            as_of=effective_at,
            limit=self._fact_limit,
        )

        self._reject_possible_truncation(
            records=rules,
            limit=self._rule_limit,
            record_type="approved rule versions",
        )
        self._reject_possible_truncation(
            records=facts,
            limit=self._fact_limit,
            record_type="approved fact versions",
        )

        return LoadedApprovedKnowledge(
            organization_id=organization_id,
            as_of=effective_at,
            rule_versions=tuple(
                self._map_rule(
                    rule,
                    organization_id=organization_id,
                    as_of=effective_at,
                )
                for rule in rules
            ),
            fact_versions=tuple(
                self._map_fact(
                    fact,
                    organization_id=organization_id,
                    as_of=effective_at,
                )
                for fact in facts
            ),
        )

    @staticmethod
    def _reject_possible_truncation(
        *,
        records: list,
        limit: int,
        record_type: str,
    ) -> None:
        if len(records) >= limit:
            raise IncompleteApprovedKnowledgeError(
                f"The number of {record_type} reached the configured "
                f"limit of {limit}. Increase the limit or implement "
                "complete retrieval before analysing this organisation."
            )

    @staticmethod
    def _validate_approval_metadata(
        *,
        status: str,
        approved_by: UUID | None,
        approved_at: datetime | None,
        record_type: str,
    ) -> None:
        if (
            status != "approved"
            or approved_by is None
            or approved_at is None
        ):
            raise IncompleteApprovedKnowledgeError(
                f"An active {record_type} record has invalid approval "
                "metadata. It cannot be used as authoritative knowledge."
            )

        if (
            approved_at.tzinfo is None
            or approved_at.utcoffset() is None
        ):
            raise IncompleteApprovedKnowledgeError(
                f"An active {record_type} record has a naive approval "
                "timestamp."
            )

    @classmethod
    def _map_rule(
        cls,
        rule,
        *,
        organization_id: UUID,
        as_of: datetime,
    ) -> ApprovedRuleVersionRecord:
        if rule.organization_id != organization_id:
            raise IncompleteApprovedKnowledgeError(
                "A rule version was returned outside the requested "
                "organisation scope."
            )

        cls._validate_approval_metadata(
            status=rule.status,
            approved_by=rule.approved_by,
            approved_at=rule.approved_at,
            record_type="rule version",
        )

        if rule.effective_from is not None:
            cls._validate_timestamp(
                rule.effective_from,
                "A rule version has a naive effective_from timestamp.",
            )

            if rule.effective_from > as_of:
                raise IncompleteApprovedKnowledgeError(
                    "A future-effective rule version was returned as active."
                )

        return ApprovedRuleVersionRecord(
            organization_id=rule.organization_id,
            rule_id=rule.rule_id,
            version_id=rule.id,
            version_number=rule.version_number,
            category=rule.category,
            rule_text=rule.rule_text,
            severity=rule.severity,
            approved_by=rule.approved_by,
            approved_at=rule.approved_at,
            effective_from=rule.effective_from,
        )

    @classmethod
    def _map_fact(
        cls,
        fact,
        *,
        organization_id: UUID,
        as_of: datetime,
    ) -> ApprovedFactVersionRecord:
        if fact.organization_id != organization_id:
            raise IncompleteApprovedKnowledgeError(
                "A fact version was returned outside the requested "
                "organisation scope."
            )

        cls._validate_approval_metadata(
            status=fact.status,
            approved_by=fact.approved_by,
            approved_at=fact.approved_at,
            record_type="fact version",
        )

        if fact.effective_from is not None:
            cls._validate_timestamp(
                fact.effective_from,
                "A fact version has a naive effective_from timestamp.",
            )

            if fact.effective_from > as_of:
                raise IncompleteApprovedKnowledgeError(
                    "A future-effective fact version was returned as active."
                )

        if fact.expires_at is not None:
            cls._validate_timestamp(
                fact.expires_at,
                "A fact version has a naive expires_at timestamp.",
            )

            if fact.expires_at <= as_of:
                raise IncompleteApprovedKnowledgeError(
                    "An expired fact version was returned as active."
                )

        fact_key = getattr(fact, "fact_key", None)
        structured_value = getattr(fact, "structured_value", None)

        if (fact_key is None) != (structured_value is None):
            raise IncompleteApprovedKnowledgeError(
                "A fact version must provide both fact_key and "
                "structured_value, or neither."
            )

        if structured_value is not None:
            if not isinstance(structured_value, dict):
                raise IncompleteApprovedKnowledgeError(
                    "A structured fact value must be a JSON object."
                )

            if not all(
                key in structured_value
                for key in ("kind", "value", "unit")
            ):
                raise IncompleteApprovedKnowledgeError(
                    "A structured fact must include kind, value and unit."
                )

        return ApprovedFactVersionRecord(
            organization_id=fact.organization_id,
            fact_id=fact.fact_id,
            version_id=fact.id,
            version_number=fact.version_number,
            fact_text=fact.fact_text,
            source_url=fact.source_url,
            approved_by=fact.approved_by,
            approved_at=fact.approved_at,
            effective_from=fact.effective_from,
            expires_at=fact.expires_at,
            fact_key=fact_key,
            structured_value=(
                dict(structured_value)
                if structured_value is not None
                else None
            ),
        )

    @staticmethod
    def _validate_timestamp(
        value: datetime,
        error_message: str,
    ) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise IncompleteApprovedKnowledgeError(error_message)