from argon2 import PasswordHasher
from sqlalchemy import func, select

from app.infrastructure.db.brand_fact_version import BrandFactVersion
from app.infrastructure.db.brand_rule_version import BrandRuleVersion
from app.infrastructure.db.organization import Organization
from app.infrastructure.db.organization_membership import (
    OrganizationMembership,
)
from app.infrastructure.db.submission import Submission
from app.infrastructure.db.submission_version import SubmissionVersion
from app.infrastructure.db.user import User
from app.infrastructure.db.seed_demo_data import (
    DEMO_FACT_VERSION_ID,
    DEMO_MEMBERSHIP_IDS,
    DEMO_ORGANIZATION_ID,
    DEMO_RULE_VERSION_ID,
    DEMO_SUBMISSION_ID,
    DEMO_SUBMISSION_VERSION_ID,
    DEMO_SUBMISSION_TEXT,
    DEMO_USER_IDS,
    seed_demo_data,
)


DEMO_PASSWORD = "Synthetic-Test-Password-739!"


def test_seed_creates_expected_demo_records(db_session):
    with db_session.begin_nested():
        seed_demo_data(db_session, DEMO_PASSWORD)

    organization = db_session.get(
        Organization,
        DEMO_ORGANIZATION_ID,
    )

    assert organization is not None
    assert organization.name == "BrandGuard Demo Organization"

    password_hasher = PasswordHasher()

    for key, user_id in DEMO_USER_IDS.items():
        user = db_session.get(User, user_id)

        assert user is not None
        assert user.email == f"demo.{key}@example.test"
        assert user.is_active is True
        assert password_hasher.verify(
            user.password_hash,
            DEMO_PASSWORD,
        )

        membership = db_session.get(
            OrganizationMembership,
            DEMO_MEMBERSHIP_IDS[key],
        )

        assert membership is not None
        assert membership.organization_id == organization.id
        assert membership.user_id == user.id

    assert db_session.get(
        BrandRuleVersion,
        DEMO_RULE_VERSION_ID,
    ).status == "approved"

    assert db_session.get(
        BrandFactVersion,
        DEMO_FACT_VERSION_ID,
    ).status == "approved"

    submission = db_session.get(
        Submission,
        DEMO_SUBMISSION_ID,
    )
    version = db_session.get(
        SubmissionVersion,
        DEMO_SUBMISSION_VERSION_ID,
    )

    assert submission is not None
    assert submission.current_version_number == 1
    assert version is not None
    assert version.original_text == DEMO_SUBMISSION_TEXT
    assert len(version.sha256) == 64


def test_seed_is_idempotent_and_preserves_existing_rows(db_session):
    with db_session.begin_nested():
        seed_demo_data(db_session, DEMO_PASSWORD)

    organization = db_session.get(
        Organization,
        DEMO_ORGANIZATION_ID,
    )
    assert organization is not None

    organization.name = "Locally customised demo organization"
    db_session.flush()

    existing_user = db_session.get(
        User,
        DEMO_USER_IDS["admin"],
    )
    assert existing_user is not None
    original_hash = existing_user.password_hash

    with db_session.begin_nested():
        seed_demo_data(
            db_session,
            "A-different-password-that-must-not-overwrite-existing",
        )

    db_session.refresh(organization)
    db_session.refresh(existing_user)

    assert organization.name == "Locally customised demo organization"
    assert existing_user.password_hash == original_hash

    user_count = db_session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.id.in_(list(DEMO_USER_IDS.values())))
    )
    membership_count = db_session.scalar(
        select(func.count())
        .select_from(OrganizationMembership)
        .where(
            OrganizationMembership.id.in_(
                list(DEMO_MEMBERSHIP_IDS.values())
            )
        )
    )

    assert user_count == 3
    assert membership_count == 3