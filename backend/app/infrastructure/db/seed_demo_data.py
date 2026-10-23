import hashlib
from datetime import datetime, timezone
from getpass import getpass
from uuid import UUID

from argon2 import PasswordHasher
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.infrastructure.db.analysis_job import AnalysisJob
from app.infrastructure.db.brand_fact import BrandFact
from app.infrastructure.db.brand_fact_version import BrandFactVersion
from app.infrastructure.db.brand_rule import BrandRule
from app.infrastructure.db.brand_rule_version import BrandRuleVersion
from app.infrastructure.db.notification import Notification
from app.infrastructure.db.organization import Organization
from app.infrastructure.db.organization_membership import (
    OrganizationMembership,
)
from app.infrastructure.db.submission import Submission
from app.infrastructure.db.submission_version import SubmissionVersion
from app.infrastructure.db.user import User


# Stable IDs make the seed repeatable across local environments.
DEMO_ORGANIZATION_ID = UUID(
    "10000000-0000-4000-8000-000000000001"
)

DEMO_USER_IDS = {
    "admin": UUID("10000000-0000-4000-8000-000000000011"),
    "creator": UUID("10000000-0000-4000-8000-000000000012"),
    "reviewer": UUID("10000000-0000-4000-8000-000000000013"),
}

DEMO_MEMBERSHIP_IDS = {
    "admin": UUID("20000000-0000-4000-8000-000000000011"),
    "creator": UUID("20000000-0000-4000-8000-000000000012"),
    "reviewer": UUID("20000000-0000-4000-8000-000000000013"),
}

DEMO_RULE_ID = UUID("30000000-0000-4000-8000-000000000001")
DEMO_RULE_VERSION_ID = UUID(
    "30000000-0000-4000-8000-000000000002"
)

DEMO_FACT_ID = UUID("40000000-0000-4000-8000-000000000001")
DEMO_FACT_VERSION_ID = UUID(
    "40000000-0000-4000-8000-000000000002"
)

DEMO_SUBMISSION_ID = UUID(
    "50000000-0000-4000-8000-000000000001"
)
DEMO_SUBMISSION_VERSION_ID = UUID(
    "50000000-0000-4000-8000-000000000002"
)

DEMO_RULE_TEXT = (
    "Use the product name FreshTrail exactly. "
    "Do not insert a space or abbreviate the name."
)

DEMO_FACT_TEXT = (
    "FreshTrail is a synthetic demonstration product used "
    "only to demonstrate the BrandGuard AI workflow."
)

DEMO_SUBMISSION_TEXT = (
    "Meet FreshTrail, a synthetic demonstration product. "
    "This sample submission is provided only to demonstrate "
    "the BrandGuard AI database workflow."
)


def _get_or_create(session, model, record_id, **fields):
    """Create a row only when its stable primary key is absent."""
    existing = session.get(model, record_id)

    if existing is not None:
        return existing

    record = model(id=record_id, **fields)
    session.add(record)
    session.flush()

    return record


def seed_demo_data(
    session: Session,
    demo_password: str,
) -> None:
    """Insert synthetic demo records without overwriting existing rows.

    The caller owns the transaction and must commit or roll it back.
    Existing demo records are intentionally left unchanged.
    """
    if not demo_password.strip():
        raise ValueError("Demo password must not be empty.")

    password_hasher = PasswordHasher()

    organization = _get_or_create(
        session,
        Organization,
        DEMO_ORGANIZATION_ID,
        name="BrandGuard Demo Organization",
    )

    users = {}

    user_details = {
        "admin": ("Demo Administrator", "admin"),
        "creator": ("Demo Creator", "creator"),
        "reviewer": ("Demo Reviewer", "reviewer"),
    }

    for key, (full_name, role_label) in user_details.items():
        user_id = DEMO_USER_IDS[key]
        existing_user = session.get(User, user_id)

        if existing_user is None:
            existing_user = User(
                id=user_id,
                full_name=full_name,
                email=f"demo.{role_label}@example.test",
                password_hash=password_hasher.hash(demo_password),
                is_active=True,
            )
            session.add(existing_user)
            session.flush()

        users[key] = existing_user

    for key, role in (
        ("admin", "admin"),
        ("creator", "creator"),
        ("reviewer", "reviewer"),
    ):
        _get_or_create(
            session,
            OrganizationMembership,
            DEMO_MEMBERSHIP_IDS[key],
            organization_id=organization.id,
            user_id=users[key].id,
            role=role,
        )

    admin_id = users["admin"].id
    creator_id = users["creator"].id
    now = datetime.now(timezone.utc)

    _get_or_create(
        session,
        BrandRule,
        DEMO_RULE_ID,
        organization_id=organization.id,
        title="FreshTrail Product Naming",
        created_by=admin_id,
    )

    _get_or_create(
        session,
        BrandRuleVersion,
        DEMO_RULE_VERSION_ID,
        organization_id=organization.id,
        rule_id=DEMO_RULE_ID,
        version_number=1,
        category="terminology",
        description="Synthetic demo terminology rule",
        rule_text=DEMO_RULE_TEXT,
        severity="medium",
        status="approved",
        created_by=admin_id,
        approved_by=admin_id,
        approved_at=now,
    )

    _get_or_create(
        session,
        BrandFact,
        DEMO_FACT_ID,
        organization_id=organization.id,
        label="Synthetic FreshTrail Demo Fact",
        created_by=admin_id,
    )

    _get_or_create(
        session,
        BrandFactVersion,
        DEMO_FACT_VERSION_ID,
        organization_id=organization.id,
        fact_id=DEMO_FACT_ID,
        version_number=1,
        fact_text=DEMO_FACT_TEXT,
        source_url=None,
        status="approved",
        created_by=admin_id,
        approved_by=admin_id,
        approved_at=now,
    )

    _get_or_create(
        session,
        Submission,
        DEMO_SUBMISSION_ID,
        organization_id=organization.id,
        title="FreshTrail Demo Submission",
        status="submitted",
        current_version_number=1,
        created_by=creator_id,
    )

    content_hash = hashlib.sha256(
        DEMO_SUBMISSION_TEXT.encode("utf-8")
    ).hexdigest()

    _get_or_create(
        session,
        SubmissionVersion,
        DEMO_SUBMISSION_VERSION_ID,
        organization_id=organization.id,
        submission_id=DEMO_SUBMISSION_ID,
        version_number=1,
        source_type="text",
        original_text=DEMO_SUBMISSION_TEXT,
        storage_key=None,
        original_filename=None,
        media_type="text/plain",
        sha256=content_hash,
        extracted_text=DEMO_SUBMISSION_TEXT,
        created_by=creator_id,
    )


def main() -> None:
    settings = get_settings()

    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured in the project-root .env file."
        )

    if not settings.database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError(
            "DATABASE_URL must use postgresql+psycopg://."
        )

    first_password = getpass(
        "Enter a demo-only password for the seeded accounts: "
    )
    confirmation = getpass("Confirm the demo password: ")

    if not first_password or not first_password.strip():
        raise SystemExit("Demo password cannot be empty.")

    if first_password != confirmation:
        raise SystemExit("Passwords do not match. No records were seeded.")

    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
    )

    try:
        with Session(engine) as session:
            with session.begin():
                seed_demo_data(session, first_password)

        print("Demo seed completed successfully.")
        print("Organisation: BrandGuard Demo Organization")
        print("Accounts:")
        print("  demo.admin@example.test")
        print("  demo.creator@example.test")
        print("  demo.reviewer@example.test")
        print("Approved demo rule, approved demo fact, and submission created.")
        print("The entered password was not printed.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()