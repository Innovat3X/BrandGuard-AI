from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.db.brand_rule import BrandRule
from app.infrastructure.db.brand_rule_version import BrandRuleVersion


RULE_CATEGORIES = {"tone", "terminology", "messaging", "other"}
RULE_SEVERITIES = {"info", "low", "medium", "high"}
RULE_VERSION_STATUSES = {"draft", "approved", "archived"}


class BrandRuleRepository:
    """Persistence operations for brand rules and immutable versions.

    The application service owns transaction boundaries, commits,
    authorization, and workflow decisions.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_rule(
        self,
        organization_id: UUID,
        title: str,
        created_by: UUID,
        category: str,
        rule_text: str,
        severity: str,
        description: str | None = None,
    ) -> tuple[BrandRule, BrandRuleVersion]:
        """Create a rule and its first draft version atomically."""
        self._validate_version_fields(category, rule_text, severity)

        if not title.strip():
            raise ValueError("Rule title must not be empty.")

        rule = BrandRule(
            organization_id=organization_id,
            title=title,
            created_by=created_by,
        )
        self._session.add(rule)
        self._session.flush()

        version = BrandRuleVersion(
            organization_id=organization_id,
            rule_id=rule.id,
            version_number=1,
            category=category,
            description=description,
            rule_text=rule_text,
            severity=severity,
            status="draft",
            created_by=created_by,
        )
        self._session.add(version)
        self._session.flush()

        return rule, version

    def get_rule(
        self,
        organization_id: UUID,
        rule_id: UUID,
    ) -> BrandRule | None:
        """Retrieve a rule within the specified organization."""
        return self._session.scalar(
            select(BrandRule).where(
                BrandRule.organization_id == organization_id,
                BrandRule.id == rule_id,
            )
        )

    def get_rule_version(
        self,
        organization_id: UUID,
        rule_id: UUID,
        version_number: int,
    ) -> BrandRuleVersion | None:
        """Retrieve an exact rule version within the organization."""
        return self._session.scalar(
            select(BrandRuleVersion).where(
                BrandRuleVersion.organization_id == organization_id,
                BrandRuleVersion.rule_id == rule_id,
                BrandRuleVersion.version_number == version_number,
            )
        )

    def list_rules(
        self,
        organization_id: UUID,
        limit: int = 100,
    ) -> list[BrandRule]:
        """List rules for one organization."""
        if limit < 1:
            raise ValueError("Limit must be at least 1.")

        statement = (
            select(BrandRule)
            .where(BrandRule.organization_id == organization_id)
            .order_by(BrandRule.created_at.desc(), BrandRule.id)
            .limit(limit)
        )
        return list(self._session.scalars(statement).all())

    def list_rule_versions(
        self,
        organization_id: UUID,
        rule_id: UUID,
    ) -> list[BrandRuleVersion] | None:
        """List a rule's versions in version-number order.

        Returns None if the rule does not belong to the organization.
        """
        rule = self.get_rule(organization_id, rule_id)
        if rule is None:
            return None

        statement = (
            select(BrandRuleVersion)
            .where(
                BrandRuleVersion.organization_id == organization_id,
                BrandRuleVersion.rule_id == rule_id,
            )
            .order_by(BrandRuleVersion.version_number)
        )
        return list(self._session.scalars(statement).all())

    def create_rule_version(
        self,
        organization_id: UUID,
        rule_id: UUID,
        category: str,
        rule_text: str,
        severity: str,
        created_by: UUID,
        description: str | None = None,
        effective_from: datetime | None = None,
    ) -> BrandRuleVersion:
        """Append a new draft version without overwriting history."""
        self._validate_version_fields(category, rule_text, severity)

        rule = self._session.scalar(
            select(BrandRule)
            .where(
                BrandRule.organization_id == organization_id,
                BrandRule.id == rule_id,
            )
            .with_for_update()
        )

        if rule is None:
            raise LookupError(
                "Brand rule not found within the specified organization."
            )

        latest_version = self._session.scalar(
            select(func.max(BrandRuleVersion.version_number)).where(
                BrandRuleVersion.organization_id == organization_id,
                BrandRuleVersion.rule_id == rule_id,
            )
        )

        next_version = 1 if latest_version is None else latest_version + 1

        version = BrandRuleVersion(
            organization_id=organization_id,
            rule_id=rule_id,
            version_number=next_version,
            category=category,
            description=description,
            rule_text=rule_text,
            severity=severity,
            status="draft",
            created_by=created_by,
            effective_from=effective_from,
        )
        self._session.add(version)
        self._session.flush()

        return version

    def approve_rule_version(
        self,
        organization_id: UUID,
        rule_id: UUID,
        version_number: int,
        approved_by: UUID,
    ) -> BrandRuleVersion:
        """Approve a draft version without changing its rule content.

        Permission checks and the decision that approval is allowed
        belong to the application service.
        """
        version = self._session.scalar(
            select(BrandRuleVersion)
            .where(
                BrandRuleVersion.organization_id == organization_id,
                BrandRuleVersion.rule_id == rule_id,
                BrandRuleVersion.version_number == version_number,
            )
            .with_for_update()
        )

        if version is None:
            raise LookupError(
                "Brand rule version not found within the specified organization."
            )

        if version.status == "approved":
            return version

        if version.status != "draft":
            raise ValueError("Only a draft rule version can be approved.")

        version.status = "approved"
        version.approved_by = approved_by
        version.approved_at = datetime.now(timezone.utc)
        self._session.flush()

        return version

    @staticmethod
    def _validate_version_fields(
        category: str,
        rule_text: str,
        severity: str,
    ) -> None:
        if category not in RULE_CATEGORIES:
            raise ValueError(f"Unsupported rule category: {category}")

        if severity not in RULE_SEVERITIES:
            raise ValueError(f"Unsupported rule severity: {severity}")

        if not rule_text.strip():
            raise ValueError("Rule text must not be empty.")