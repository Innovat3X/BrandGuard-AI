"""Application service for versioned brand facts."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db import BrandFact, BrandFactVersion
from app.infrastructure.db.repositories.brand_fact_repository import (
    BrandFactRepository,
)


class BrandFactNotFoundError(LookupError):
    """A fact does not exist in the requested organisation."""


class BrandFactConflictError(ValueError):
    """A fact cannot transition to the requested state."""


class BrandFactService:
    """Coordinate repository operations and transaction boundaries."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repository = BrandFactRepository(session)

    def list_facts(
        self,
        *,
        organization_id: UUID,
        limit: int = 100,
    ) -> list[tuple[BrandFact, list[BrandFactVersion]]]:
        """Return organisation-scoped facts with their version history."""
        facts = self._repository.list_facts(
            organization_id=organization_id,
            limit=limit,
        )

        result: list[tuple[BrandFact, list[BrandFactVersion]]] = []

        for fact in facts:
            versions = self._repository.list_fact_versions(
                organization_id=organization_id,
                fact_id=fact.id,
            )
            if versions is not None:
                result.append((fact, versions))

        return result

    def create_draft_fact(
        self,
        *,
        organization_id: UUID,
        created_by: UUID,
        label: str,
        fact_text: str,
        source_url: str | None = None,
        effective_from: datetime | None = None,
        expires_at: datetime | None = None,
        fact_key: str | None = None,
        structured_value: dict[str, Any] | None = None,
    ) -> tuple[BrandFact, list[BrandFactVersion]]:
        """Create a draft fact and commit it as one transaction."""
        try:
            fact, version = self._repository.create_fact(
                organization_id=organization_id,
                label=label,
                fact_text=fact_text,
                created_by=created_by,
                source_url=source_url,
                effective_from=effective_from,
                expires_at=expires_at,
                fact_key=fact_key,
                structured_value=structured_value,
            )

            self._session.commit()
            self._session.refresh(fact)
            self._session.refresh(version)

            return fact, [version]

        except Exception:
            self._session.rollback()
            raise

    def approve_latest_draft(
        self,
        *,
        organization_id: UUID,
        fact_id: UUID,
        approved_by: UUID,
    ) -> tuple[BrandFact, list[BrandFactVersion]]:
        """Approve the latest draft while preserving version history."""
        try:
            fact = self._repository.get_fact(
                organization_id=organization_id,
                fact_id=fact_id,
            )

            if fact is None:
                raise BrandFactNotFoundError(
                    "Brand fact not found."
                )

            versions = self._repository.list_fact_versions(
                organization_id=organization_id,
                fact_id=fact_id,
            )

            if not versions:
                raise BrandFactNotFoundError(
                    "No versions were found for this brand fact."
                )

            latest_version = versions[-1]

            if latest_version.status != "draft":
                raise BrandFactConflictError(
                    "The latest fact version is not a draft."
                )

            self._repository.approve_fact_version(
                organization_id=organization_id,
                fact_id=fact_id,
                version_number=latest_version.version_number,
                approved_by=approved_by,
            )

            self._session.commit()

            fact = self._repository.get_fact(
                organization_id=organization_id,
                fact_id=fact_id,
            )
            versions = self._repository.list_fact_versions(
                organization_id=organization_id,
                fact_id=fact_id,
            )

            if fact is None or versions is None:
                raise BrandFactNotFoundError(
                    "Brand fact could not be retrieved after approval."
                )

            return fact, versions

        except Exception:
            self._session.rollback()
            raise
    def update_latest_draft(
        self,
        *,
        organization_id: UUID,
        fact_id: UUID,
        label: str,
        fact_text: str,
        source_url: str | None = None,
        effective_from: datetime | None = None,
        expires_at: datetime | None = None,
        fact_key: str | None = None,
        structured_value: dict[str, Any] | None = None,
    ) -> tuple[BrandFact, list[BrandFactVersion]]:
        """Edit the latest draft without changing approved fact history."""
        try:
            versions = self._repository.list_fact_versions(
                organization_id=organization_id,
                fact_id=fact_id,
            )
            if versions is None or not versions:
                raise BrandFactNotFoundError("Brand fact not found.")

            if versions[-1].status != "draft":
                raise BrandFactConflictError(
                    "Only the latest draft fact version can be updated. "
                    "Create a new draft version before making changes."
                )

            updated = self._repository.update_draft_fact(
                organization_id=organization_id,
                fact_id=fact_id,
                label=label,
                fact_text=fact_text,
                source_url=source_url,
                effective_from=effective_from,
                expires_at=expires_at,
                fact_key=fact_key,
                structured_value=structured_value,
            )
            if updated is None:
                raise BrandFactNotFoundError("Brand fact not found.")

            fact, version = updated
            self._session.commit()
            self._session.refresh(fact)
            self._session.refresh(version)

            refreshed_versions = self._repository.list_fact_versions(
                organization_id=organization_id,
                fact_id=fact_id,
            )
            if refreshed_versions is None:
                raise BrandFactNotFoundError(
                    "Brand fact could not be retrieved after updating."
                )

            return fact, refreshed_versions
        except (BrandFactNotFoundError, BrandFactConflictError):
            self._session.rollback()
            raise
        except ValueError as exc:
            self._session.rollback()
            if "latest draft fact version" in str(exc):
                raise BrandFactConflictError(str(exc)) from exc
            raise
        except Exception:
            self._session.rollback()
            raise

    def create_draft_version(
        self,
        *,
        organization_id: UUID,
        fact_id: UUID,
        created_by: UUID,
        fact_text: str,
        source_url: str | None = None,
        effective_from: datetime | None = None,
        expires_at: datetime | None = None,
        fact_key: str | None = None,
        structured_value: dict[str, Any] | None = None,
    ) -> tuple[BrandFact, list[BrandFactVersion]]:
        """Append a draft version while retaining the complete fact history."""
        try:
            fact = self._repository.get_fact(
                organization_id=organization_id,
                fact_id=fact_id,
            )
            if fact is None:
                raise BrandFactNotFoundError("Brand fact not found.")

            existing_versions = self._repository.list_fact_versions(
                organization_id=organization_id,
                fact_id=fact_id,
            )
            if existing_versions is None:
                raise BrandFactNotFoundError("Brand fact not found.")
            if existing_versions and existing_versions[-1].status == "draft":
                raise BrandFactConflictError(
                    "A draft fact version already exists. Update or approve "
                    "it before creating another version."
                )

            version = self._repository.create_fact_version(
                organization_id=organization_id,
                fact_id=fact_id,
                fact_text=fact_text,
                created_by=created_by,
                source_url=source_url,
                effective_from=effective_from,
                expires_at=expires_at,
                fact_key=fact_key,
                structured_value=structured_value,
            )
            self._session.commit()
            self._session.refresh(fact)
            self._session.refresh(version)

            versions = self._repository.list_fact_versions(
                organization_id=organization_id,
                fact_id=fact_id,
            )
            if versions is None:
                raise BrandFactNotFoundError(
                    "Brand fact could not be retrieved after version creation."
                )
            return fact, versions
        except (BrandFactNotFoundError, BrandFactConflictError):
            self._session.rollback()
            raise
        except LookupError as exc:
            self._session.rollback()
            raise BrandFactNotFoundError(str(exc)) from exc
        except Exception:
            self._session.rollback()
            raise