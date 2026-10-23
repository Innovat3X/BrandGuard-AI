from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.audit_event import AuditEvent


class AuditEventRepository:
    """Persistence operations for append-only audit events.

    Application services own transaction boundaries and commits.
    Audit events are created as history records; this repository
    intentionally exposes no update or delete operations.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_event(
        self,
        organization_id: UUID,
        action: str,
        entity_type: str,
        actor_user_id: UUID | None = None,
        entity_id: UUID | None = None,
        details: dict | None = None,
    ) -> AuditEvent:
        """Append an audit event within the specified organization.

        Callers must provide trusted organization context and ensure
        details contain no passwords, tokens, or unnecessary sensitive data.
        """
        if not action.strip():
            raise ValueError("Audit action must not be empty.")

        if not entity_type.strip():
            raise ValueError("Audit entity type must not be empty.")

        event = AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )

        self._session.add(event)
        self._session.flush()

        return event

    def get_event(
        self,
        organization_id: UUID,
        event_id: UUID,
    ) -> AuditEvent | None:
        """Retrieve one audit event within its organization."""
        statement = select(AuditEvent).where(
            AuditEvent.organization_id == organization_id,
            AuditEvent.id == event_id,
        )

        return self._session.scalar(statement)

    def list_for_entity(
        self,
        organization_id: UUID,
        entity_type: str,
        entity_id: UUID,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """List audit history for one entity in chronological order."""
        if limit < 1:
            raise ValueError("Limit must be at least 1.")

        statement = (
            select(AuditEvent)
            .where(
                AuditEvent.organization_id == organization_id,
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id,
            )
            .order_by(AuditEvent.created_at, AuditEvent.id)
            .limit(limit)
        )

        return list(self._session.scalars(statement).all())

    def list_recent(
        self,
        organization_id: UUID,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """List the most recent audit events for one organization."""
        if limit < 1:
            raise ValueError("Limit must be at least 1.")

        statement = (
            select(AuditEvent)
            .where(AuditEvent.organization_id == organization_id)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
        )

        return list(self._session.scalars(statement).all())