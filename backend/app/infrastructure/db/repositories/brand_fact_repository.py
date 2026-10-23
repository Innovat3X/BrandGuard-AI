
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.infrastructure.db.brand_fact import BrandFact
from app.infrastructure.db.brand_fact_version import BrandFactVersion


FACT_VERSION_STATUSES = {"draft", "approved", "archived"}


class BrandFactRepository:
    """Persistence operations for brand facts and immutable versions.

    The application service owns transaction boundaries, commits,
    authorization, and approval workflow decisions.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_fact(
        self,
        organization_id: UUID,
        label: str,
        fact_text: str,
        created_by: UUID,
        source_url: str | None = None,
        effective_from: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[BrandFact, BrandFactVersion]:
        """Create a fact and its first draft version in one transaction."""
        self._validate_version_fields(fact_text)

        if not label.strip():
            raise ValueError("Fact label must not be empty.")

        self._validate_dates(effective_from, expires_at)

        fact = BrandFact(
            organization_id=organization_id,
            label=label,
            created_by=created_by,
        )
        self._session.add(fact)
        self._session.flush()

        version = BrandFactVersion(
            organization_id=organization_id,
            fact_id=fact.id,
            version_number=1,
            fact_text=fact_text,
            source_url=source_url,
            status="draft",
            effective_from=effective_from,
            expires_at=expires_at,
            created_by=created_by,
        )
        self._session.add(version)
        self._session.flush()

        return fact, version

    def get_fact(
        self,
        organization_id: UUID,
        fact_id: UUID,
    ) -> BrandFact | None:
        """Retrieve a fact within the specified organization."""
        return self._session.scalar(
            select(BrandFact).where(
                BrandFact.organization_id == organization_id,
                BrandFact.id == fact_id,
            )
        )

    def get_fact_version(
        self,
        organization_id: UUID,
        fact_id: UUID,
        version_number: int,
    ) -> BrandFactVersion | None:
        """Retrieve an exact fact version within the organization."""
        return self._session.scalar(
            select(BrandFactVersion).where(
                BrandFactVersion.organization_id == organization_id,
                BrandFactVersion.fact_id == fact_id,
                BrandFactVersion.version_number == version_number,
            )
        )

    def list_facts(
        self,
        organization_id: UUID,
        limit: int = 100,
    ) -> list[BrandFact]:
        """List facts for one organization."""
        if limit < 1:
            raise ValueError("Limit must be at least 1.")

        statement = (
            select(BrandFact)
            .where(BrandFact.organization_id == organization_id)
            .order_by(
                BrandFact.created_at.desc(),
                BrandFact.id,
            )
            .limit(limit)
        )

        return list(self._session.scalars(statement).all())

    def list_fact_versions(
        self,
        organization_id: UUID,
        fact_id: UUID,
    ) -> list[BrandFactVersion] | None:
        """List versions in version-number order.

        Returns None when the fact is not found within the organization.
        """
        if self.get_fact(organization_id, fact_id) is None:
            return None

        statement = (
            select(BrandFactVersion)
            .where(
                BrandFactVersion.organization_id == organization_id,
                BrandFactVersion.fact_id == fact_id,
            )
            .order_by(BrandFactVersion.version_number)
        )

        return list(self._session.scalars(statement).all())

    def list_approved_fact_versions(
        self,
        organization_id: UUID,
        limit: int = 100,
    ) -> list[BrandFactVersion]:
        """List approved fact versions, including their historical versions.

        Use list_active_fact_versions() when retrieving facts for
        current analysis. This method deliberately does not apply
        effective-date or expiry filtering.
        """
        if limit < 1:
            raise ValueError("Limit must be at least 1.")

        statement = (
            select(BrandFactVersion)
            .where(
                BrandFactVersion.organization_id == organization_id,
                BrandFactVersion.status == "approved",
            )
            .order_by(
                BrandFactVersion.created_at.desc(),
                BrandFactVersion.id,
            )
            .limit(limit)
        )

        return list(self._session.scalars(statement).all())

    def list_active_fact_versions(
        self,
        organization_id: UUID,
        as_of: datetime | None = None,
        limit: int = 100,
    ) -> list[BrandFactVersion]:
        """Return the latest applicable approved version of each fact.

        Draft and archived versions are excluded. A version is applicable
        when effective_from is absent or has passed, and expires_at is
        absent or is still in the future.

        When multiple eligible approved versions exist for a fact, the
        highest eligible version number is returned. Historical versions
        remain unchanged.

        The application service remains responsible for any additional
        evidence-quality or domain-specific claim verification rules.
        """
        if limit < 1:
            raise ValueError("Limit must be at least 1.")

        effective_at = as_of or datetime.now(timezone.utc)

        if (
            effective_at.tzinfo is None
            or effective_at.utcoffset() is None
        ):
            raise ValueError("as_of must be timezone-aware.")

        eligible_versions = (
            select(
                BrandFactVersion.id.label("version_id"),
                func.row_number()
                .over(
                    partition_by=BrandFactVersion.fact_id,
                    order_by=BrandFactVersion.version_number.desc(),
                )
                .label("version_rank"),
            )
            .where(
                BrandFactVersion.organization_id == organization_id,
                BrandFactVersion.status == "approved",
                or_(
                    BrandFactVersion.effective_from.is_(None),
                    BrandFactVersion.effective_from <= effective_at,
                ),
                or_(
                    BrandFactVersion.expires_at.is_(None),
                    BrandFactVersion.expires_at > effective_at,
                ),
            )
            .subquery()
        )

        statement = (
            select(BrandFactVersion)
            .join(
                eligible_versions,
                BrandFactVersion.id == eligible_versions.c.version_id,
            )
            .where(
                BrandFactVersion.organization_id == organization_id,
                eligible_versions.c.version_rank == 1,
            )
            .order_by(BrandFactVersion.fact_id)
            .limit(limit)
        )

        return list(self._session.scalars(statement).all())

    def create_fact_version(
        self,
        organization_id: UUID,
        fact_id: UUID,
        fact_text: str,
        created_by: UUID,
        source_url: str | None = None,
        effective_from: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> BrandFactVersion:
        """Append a draft version without overwriting fact history."""
        self._validate_version_fields(fact_text)
        self._validate_dates(effective_from, expires_at)

        fact = self._session.scalar(
            select(BrandFact)
            .where(
                BrandFact.organization_id == organization_id,
                BrandFact.id == fact_id,
            )
            .with_for_update()
        )

        if fact is None:
            raise LookupError(
                "Brand fact not found within the specified organization."
            )

        latest_version = self._session.scalar(
            select(func.max(BrandFactVersion.version_number)).where(
                BrandFactVersion.organization_id == organization_id,
                BrandFactVersion.fact_id == fact_id,
            )
        )

        next_version = (
            1 if latest_version is None else latest_version + 1
        )

        version = BrandFactVersion(
            organization_id=organization_id,
            fact_id=fact_id,
            version_number=next_version,
            fact_text=fact_text,
            source_url=source_url,
            status="draft",
            effective_from=effective_from,
            expires_at=expires_at,
            created_by=created_by,
        )
        self._session.add(version)
        self._session.flush()

        return version

    def approve_fact_version(
        self,
        organization_id: UUID,
        fact_id: UUID,
        version_number: int,
        approved_by: UUID,
    ) -> BrandFactVersion:
        """Approve a draft version and record its approval metadata.

        Authorization must be checked by the application service.
        Re-approving an already approved version preserves its original
        approval timestamp and approver.
        """
        version = self._session.scalar(
            select(BrandFactVersion)
            .where(
                BrandFactVersion.organization_id == organization_id,
                BrandFactVersion.fact_id == fact_id,
                BrandFactVersion.version_number == version_number,
            )
            .with_for_update()
        )

        if version is None:
            raise LookupError(
                "Brand fact version not found within the specified organization."
            )

        if version.status == "approved":
            return version

        if version.status != "draft":
            raise ValueError(
                "Only a draft fact version can be approved."
            )

        version.status = "approved"
        version.approved_by = approved_by
        version.approved_at = datetime.now(timezone.utc)
        self._session.flush()

        return version

    @staticmethod
    def _validate_version_fields(fact_text: str) -> None:
        if not fact_text.strip():
            raise ValueError("Fact text must not be empty.")

    @staticmethod
    def _validate_dates(
        effective_from: datetime | None,
        expires_at: datetime | None,
    ) -> None:
        if (
            effective_from is not None
            and (
                effective_from.tzinfo is None
                or effective_from.utcoffset() is None
            )
        ):
            raise ValueError("effective_from must be timezone-aware.")

        if (
            expires_at is not None
            and (
                expires_at.tzinfo is None
                or expires_at.utcoffset() is None
            )
        ):
            raise ValueError("expires_at must be timezone-aware.")

        if (
            effective_from is not None
            and expires_at is not None
            and expires_at <= effective_from
        ):
            raise ValueError(
                "expires_at must be later than effective_from."
            )
