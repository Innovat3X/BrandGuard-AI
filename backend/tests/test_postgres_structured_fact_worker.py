
"""PostgreSQL integration test for structured fact verification and retrieval."""

from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.v1.auth import AuthenticatedActor, get_current_actor
from app.infrastructure.db import (
    AnalysisJob,
    Finding,
    Organization,
    Submission,
    User,
)
from app.infrastructure.db.repositories.analysis_job_repository import (
    AnalysisJobRepository,
)
from app.infrastructure.db.repositories.brand_fact_repository import (
    BrandFactRepository,
)
from app.infrastructure.db.repositories.brand_rule_repository import (
    BrandRuleRepository,
)
from app.infrastructure.db.repositories.submission_repository import (
    SubmissionRepository,
)
from app.infrastructure.db.session import get_db
from app.main import app
from app.services.analysis_worker_factory import (
    build_analysis_worker_service,
)


def test_postgres_structured_fact_finding_persists_and_is_retrievable(
    db_session,
):
    """Run a real worker and retrieve its saved finding through the API."""

    suffix = uuid4().hex

    organization = Organization(
        name=f"Structured fact integration {suffix}",
    )
    user = User(
        full_name="Structured Fact Integration User",
        email=f"{suffix}@example.com",
        password_hash="test-only-password-hash",
    )

    db_session.add_all([organization, user])
    db_session.flush()

    submissions = SubmissionRepository(db_session)

    submission = submissions.create_submission(
        organization_id=organization.id,
        title="Structured price verification",
        created_by=user.id,
    )

    content_text = "The price is ₹999."

    version = submissions.create_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=1,
        source_type="text",
        sha256="a" * 64,
        created_by=user.id,
        original_text=content_text,
    )

    # Create and approve a real structured price fact.
    facts = BrandFactRepository(db_session)

    fact, fact_version = facts.create_fact(
        organization_id=organization.id,
        label="Product price",
        fact_text="The approved product price is ₹1299.",
        created_by=user.id,
        source_url="https://example.com/product",
        fact_key="product_price",
        structured_value={
            "kind": "currency",
            "value": "1299",
            "unit": "INR",
        },
    )

    fact_version = facts.approve_fact_version(
        organization_id=organization.id,
        fact_id=fact.id,
        version_number=fact_version.version_number,
        approved_by=user.id,
    )

    # Supply one supported terminology rule.
    rules = BrandRuleRepository(db_session)

    rule, rule_version = rules.create_rule(
        organization_id=organization.id,
        title="Approved terminology",
        created_by=user.id,
        category="terminology",
        rule_text="forbidden_term: awesome",
        severity="medium",
        description="Integration-test terminology rule",
    )

    rules.approve_rule_version(
        organization_id=organization.id,
        rule_id=rule.id,
        version_number=rule_version.version_number,
        approved_by=user.id,
    )

    # Queue a real analysis job in PostgreSQL.
    jobs = AnalysisJobRepository(db_session)

    job = jobs.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=version.id,
        idempotency_key=f"structured-price-{suffix}",
    )

    queue = Mock()

    # Keep the test deterministic: no external AI service or API key.
    # The price claim should still be checked against the approved fact.
    with patch(
        "app.services.analysis_pipeline_factory.get_settings",
        return_value=type(
            "SettingsStub",
            (),
            {"ai_provider": "disabled"},
        )(),
    ):
        worker = build_analysis_worker_service(
            db_session,
            queue,
        )
        result = worker.process_job(job.id)

    assert result is not None
    assert result.status == "partial"
    assert result.finding_count == 1

    # Reload records to verify the persisted database state.
    db_session.expire_all()

    saved_job = db_session.scalar(
        select(AnalysisJob).where(
            AnalysisJob.organization_id == organization.id,
            AnalysisJob.id == job.id,
        )
    )

    assert saved_job is not None
    assert saved_job.status == "partial"
    assert saved_job.completed_at is not None

    saved_findings = list(
        db_session.scalars(
            select(Finding).where(
                Finding.organization_id == organization.id,
                Finding.analysis_job_id == job.id,
                Finding.submission_version_id == version.id,
            )
        ).all()
    )

    assert len(saved_findings) == 1

    saved_finding = saved_findings[0]

    assert saved_finding.category == "factual_claim"
    assert saved_finding.result == "conflict"
    assert saved_finding.source_fact_version_id == fact_version.id
    assert saved_finding.source_rule_version_id is None
    assert saved_finding.finding_fingerprint
    assert saved_finding.requires_human_review is True
    assert saved_finding.suggested_correction == "The price is ₹1299."

    # Exercise the findings API against the persisted database row.
    actor = AuthenticatedActor(
        user=user,
        organization=organization,
        role="reviewer",
    )

    previous_db_override = app.dependency_overrides.get(get_db)
    previous_actor_override = app.dependency_overrides.get(
        get_current_actor
    )

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_actor] = lambda: actor

    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/submissions/{submission.id}/findings",
                params={"version": 1},
            )
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override

        if previous_actor_override is None:
            app.dependency_overrides.pop(get_current_actor, None)
        else:
            app.dependency_overrides[get_current_actor] = (
                previous_actor_override
            )

    assert response.status_code == 200

    payload = response.json()

    assert payload["submission_id"] == str(submission.id)
    assert payload["version_number"] == 1
    assert len(payload["findings"]) == 1

    api_finding = payload["findings"][0]

    assert api_finding["id"] == str(saved_finding.id)
    assert api_finding["category"] == "factual_claim"
    assert api_finding["result"] == "conflict"
    assert api_finding["source_fact_version_id"] == str(fact_version.id)
    assert api_finding["evidence"]["submitted_text"] == "₹999"
    assert (
        api_finding["evidence"]["approved_reference"]
        == "The approved product price is ₹1299."
    )
    assert (
        api_finding["evidence"]["source_url"]
        == "https://example.com/product"
    )
    assert api_finding["suggested_correction"] == "The price is ₹1299."
    assert api_finding["detection_method"] == "deterministic"
    assert api_finding["requires_human_review"] is True

    # Analysis leaves publication approval to a human reviewer.
    saved_submission = db_session.scalar(
        select(Submission).where(
            Submission.organization_id == organization.id,
            Submission.id == submission.id,
        )
    )

    assert saved_submission is not None
    assert saved_submission.status == "under_review"

    queue.enqueue_analysis.assert_not_called()
