"""Application service for organisation-scoped, versioned brand rules."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db import BrandRule, BrandRuleVersion
from app.infrastructure.db.repositories.brand_rule_repository import (
    BrandRuleRepository,
)


class BrandRuleNotFoundError(LookupError):
    """A rule does not exist in the requested organisation."""


class BrandRuleConflictError(ValueError):
    """A requested operation conflicts with the current version state."""


class BrandRuleService:
    """Coordinate repository operations and transaction boundaries."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repository = BrandRuleRepository(session)

    def list_rules(
        self,
        *,
        organization_id: UUID,
        limit: int = 100,
    ) -> list[tuple[BrandRule, list[BrandRuleVersion]]]:
        """Return organisation-scoped rules with complete version history."""
        rules = self._repository.list_rules(
            organization_id=organization_id,
            limit=limit,
        )
        result: list[tuple[BrandRule, list[BrandRuleVersion]]] = []

        for rule in rules:
            versions = self._repository.list_rule_versions(
                organization_id=organization_id,
                rule_id=rule.id,
            )
            if versions is not None:
                result.append((rule, versions))

        return result

    def create_draft_rule(
        self,
        *,
        organization_id: UUID,
        created_by: UUID,
        title: str,
        category: str,
        rule_text: str,
        severity: str,
        description: str | None = None,
    ) -> tuple[BrandRule, list[BrandRuleVersion]]:
        """Create a rule and its initial draft version."""
        try:
            rule, version = self._repository.create_rule(
                organization_id=organization_id,
                title=title,
                created_by=created_by,
                category=category,
                rule_text=rule_text,
                severity=severity,
                description=description,
            )
            self._session.commit()
            self._session.refresh(rule)
            self._session.refresh(version)
            return rule, [version]
        except Exception:
            self._session.rollback()
            raise

    def update_latest_draft(
        self,
        *,
        organization_id: UUID,
        rule_id: UUID,
        title: str,
        category: str,
        rule_text: str,
        severity: str,
        description: str | None = None,
    ) -> tuple[BrandRule, list[BrandRuleVersion]]:
        """Update only the latest draft; approved history is immutable."""
        try:
            versions = self._repository.list_rule_versions(
                organization_id=organization_id,
                rule_id=rule_id,
            )
            if versions is None:
                raise BrandRuleNotFoundError("Brand rule not found.")
            if not versions:
                raise BrandRuleNotFoundError(
                    "No versions were found for this brand rule."
                )
            if versions[-1].status != "draft":
                raise BrandRuleConflictError(
                    "Only the latest draft rule version can be updated. "
                    "Create a new draft version before making changes."
                )

            updated = self._repository.update_draft_rule(
                organization_id=organization_id,
                rule_id=rule_id,
                title=title,
                category=category,
                rule_text=rule_text,
                severity=severity,
                description=description,
            )
            if updated is None:
                raise BrandRuleNotFoundError("Brand rule not found.")

            rule, version = updated
            self._session.commit()
            self._session.refresh(rule)
            self._session.refresh(version)
            refreshed_versions = self._repository.list_rule_versions(
                organization_id=organization_id,
                rule_id=rule_id,
            )
            if refreshed_versions is None:
                raise BrandRuleNotFoundError(
                    "Brand rule could not be retrieved after updating."
                )
            return rule, refreshed_versions
        except BrandRuleNotFoundError:
            self._session.rollback()
            raise
        except BrandRuleConflictError:
            self._session.rollback()
            raise
        except ValueError as exc:
            self._session.rollback()
            if "Only the latest draft rule version" in str(exc):
                raise BrandRuleConflictError(str(exc)) from exc
            raise
        except Exception:
            self._session.rollback()
            raise

    def create_draft_version(
        self,
        *,
        organization_id: UUID,
        rule_id: UUID,
        created_by: UUID,
        category: str,
        rule_text: str,
        severity: str,
        description: str | None = None,
        effective_from: datetime | None = None,
    ) -> tuple[BrandRule, list[BrandRuleVersion]]:
        """Append a new draft version and retain all previous versions."""
        try:
            rule = self._repository.get_rule(
                organization_id=organization_id,
                rule_id=rule_id,
            )
            if rule is None:
                raise BrandRuleNotFoundError("Brand rule not found.")

            existing_versions = self._repository.list_rule_versions(
                organization_id=organization_id,
                rule_id=rule_id,
            )
            if existing_versions is None:
                raise BrandRuleNotFoundError("Brand rule not found.")
            if existing_versions and existing_versions[-1].status == "draft":
                raise BrandRuleConflictError(
                    "A draft version already exists. Update or approve it "
                    "before creating another version."
                )

            self._repository.create_rule_version(
                organization_id=organization_id,
                rule_id=rule_id,
                category=category,
                rule_text=rule_text,
                severity=severity,
                created_by=created_by,
                description=description,
                effective_from=effective_from,
            )
            self._session.commit()
            self._session.refresh(rule)
            versions = self._repository.list_rule_versions(
                organization_id=organization_id,
                rule_id=rule_id,
            )
            if versions is None:
                raise BrandRuleNotFoundError(
                    "Brand rule could not be retrieved after version creation."
                )
            return rule, versions
        except Exception:
            self._session.rollback()
            raise

    def approve_latest_draft(
        self,
        *,
        organization_id: UUID,
        rule_id: UUID,
        approved_by: UUID,
    ) -> tuple[BrandRule, list[BrandRuleVersion]]:
        """Approve the latest draft and retain the complete version history."""
        try:
            rule = self._repository.get_rule(
                organization_id=organization_id,
                rule_id=rule_id,
            )
            if rule is None:
                raise BrandRuleNotFoundError("Brand rule not found.")

            versions = self._repository.list_rule_versions(
                organization_id=organization_id,
                rule_id=rule_id,
            )
            if not versions:
                raise BrandRuleNotFoundError(
                    "No versions were found for this brand rule."
                )
            latest_version = versions[-1]
            if latest_version.status != "draft":
                raise BrandRuleConflictError(
                    "The latest brand rule version is not a draft."
                )

            self._repository.approve_rule_version(
                organization_id=organization_id,
                rule_id=rule_id,
                version_number=latest_version.version_number,
                approved_by=approved_by,
            )
            self._session.commit()

            refreshed_rule = self._repository.get_rule(
                organization_id=organization_id,
                rule_id=rule_id,
            )
            refreshed_versions = self._repository.list_rule_versions(
                organization_id=organization_id,
                rule_id=rule_id,
            )
            if refreshed_rule is None or refreshed_versions is None:
                raise BrandRuleNotFoundError(
                    "Brand rule could not be retrieved after approval."
                )
            return refreshed_rule, refreshed_versions
        except (BrandRuleNotFoundError, BrandRuleConflictError):
            self._session.rollback()
            raise
        except Exception:
            self._session.rollback()
            raise
