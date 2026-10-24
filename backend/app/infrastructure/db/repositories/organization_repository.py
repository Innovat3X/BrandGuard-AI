from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.organization import Organization


class OrganizationRepository:
    """Database operations for organisation records.

    Application services own authorization and transaction boundaries.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_organization(self, name: str) -> Organization:
        """Create an organisation with a validated name."""
        normalized_name = name.strip()

        if not normalized_name:
            raise ValueError("Organization name must not be empty.")

        organization = Organization(name=normalized_name)

        self._session.add(organization)
        self._session.flush()

        return organization

    def get_by_id(
        self,
        organization_id: UUID,
    ) -> Organization | None:
        """Retrieve an organisation by its primary key."""
        return self._session.scalar(
            select(Organization).where(
                Organization.id == organization_id
            )
        )