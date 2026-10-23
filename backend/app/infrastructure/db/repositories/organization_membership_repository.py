from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.organization_membership import (
    OrganizationMembership,
)


VALID_ROLES = {"admin", "creator", "reviewer"}


class OrganizationMembershipRepository:
    """Database operations for organisation memberships.

    Authorization and transaction boundaries belong to application
    services. Every membership lookup is scoped to an organisation.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_membership(
        self,
        organization_id: UUID,
        user_id: UUID,
        role: str,
    ) -> OrganizationMembership:
        """Create a membership for a user in an organisation."""
        self._validate_role(role)

        membership = OrganizationMembership(
            organization_id=organization_id,
            user_id=user_id,
            role=role,
        )

        self._session.add(membership)
        self._session.flush()

        return membership

    def get_membership(
        self,
        organization_id: UUID,
        user_id: UUID,
    ) -> OrganizationMembership | None:
        """Retrieve a user's membership in a specific organisation."""
        statement = select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )

        return self._session.scalar(statement)

    def get_by_id(
        self,
        organization_id: UUID,
        membership_id: UUID,
    ) -> OrganizationMembership | None:
        """Retrieve a membership within the specified organisation."""
        statement = select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.id == membership_id,
        )

        return self._session.scalar(statement)

    def list_for_organization(
        self,
        organization_id: UUID,
        limit: int = 100,
    ) -> list[OrganizationMembership]:
        """List memberships belonging to one organisation."""
        if limit < 1:
            raise ValueError("Limit must be at least 1.")

        statement = (
            select(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id
            )
            .order_by(
                OrganizationMembership.created_at,
                OrganizationMembership.id,
            )
            .limit(limit)
        )

        return list(self._session.scalars(statement).all())

    def update_role(
        self,
        organization_id: UUID,
        user_id: UUID,
        role: str,
    ) -> OrganizationMembership | None:
        """Update a user's role within the specified organisation.

        Returns None when the membership does not exist.
        Authorization must be enforced by the application service.
        """
        self._validate_role(role)

        statement = (
            select(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user_id,
            )
            .with_for_update()
        )

        membership = self._session.scalar(statement)

        if membership is None:
            return None

        membership.role = role
        self._session.flush()

        return membership

    @staticmethod
    def _validate_role(role: str) -> None:
        if role not in VALID_ROLES:
            raise ValueError(f"Unsupported membership role: {role}")