
"""Worker integration test for structured approved-fact verification."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from app.infrastructure.db.analysis_knowledge_loader import (
    ApprovedFactVersionRecord,
    ApprovedRuleVersionRecord,
)
from app.infrastructure.db.submission_version_loader import (
    DatabaseLoadedSubmissionVersion,
)
from app.services.analysis_worker_factory import (
    build_analysis_worker_service,
)


APPROVED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeSession:
    """Track worker transaction boundaries without a real database."""

    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeAnalysisJobRepository:
    """Capture findings handed from the worker to persistence."""

    def __init__(self, job):
        self.job = job
        self.persisted = None

    def claim_queued_job(self, job_id):
        if job_id != self.job.id or self.job.status != "queued":
            return None

        self.job.status = "processing"
        self.job.attempts += 1
        return self.job

    def persist_findings_and_finish_job(self, **kwargs):
        self.persisted = kwargs
        self.job.status = kwargs["final_status"]
        return True


def test_worker_verifies_structured_price_and_hands_finding_to_persistence(
    monkeypatch,
):
    organization_id = uuid4()
    job_id = uuid4()
    submission_id = uuid4()
    submission_version_id = uuid4()
    fact_id = uuid4()
    fact_version_id = uuid4()

    content_text = "The price is ₹999."

    job = SimpleNamespace(
        id=job_id,
        organization_id=organization_id,
        submission_version_id=submission_version_id,
        requested_checks=None,
        status="queued",
        attempts=0,
    )

    # The worker's knowledge loader supplies approved,
    # organisation-scoped fact versions.
    approved_fact = ApprovedFactVersionRecord(
        organization_id=organization_id,
        fact_id=fact_id,
        version_id=fact_version_id,
        version_number=1,
        fact_text="The approved product price is ₹1299.",
        source_url="https://example.com/product",
        approved_by=uuid4(),
        approved_at=APPROVED_AT,
        effective_from=None,
        expires_at=None,
        fact_key="product_price",
        structured_value={
            "kind": "currency",
            "value": "1299",
            "unit": "INR",
        },
    )

    # Supply one parseable terminology rule alongside the structured fact.
    approved_rule = ApprovedRuleVersionRecord(
        organization_id=organization_id,
        rule_id=uuid4(),
        version_id=uuid4(),
        version_number=1,
        category="terminology",
        rule_text="forbidden_term: awesome",
        severity="medium",
        approved_by=uuid4(),
        approved_at=APPROVED_AT,
        effective_from=None,
    )

    knowledge = SimpleNamespace(
        organization_id=organization_id,
        as_of=APPROVED_AT,
        rule_versions=(approved_rule,),
        fact_versions=(approved_fact,),
    )

    knowledge_loader = Mock()
    knowledge_loader.load.return_value = knowledge

    def build_fake_knowledge_loader(_session, **_kwargs):
        return knowledge_loader

    monkeypatch.setattr(
        "app.services.analysis_pipeline_factory."
        "DatabaseAnalysisKnowledgeLoader",
        build_fake_knowledge_loader,
    )

    loaded_versions = []

    class StubSubmissionVersionLoader:
        def __init__(self, session):
            self.session = session

        def load_submission_version(
            self,
            *,
            organization_id,
            submission_version_id,
        ):
            loaded_versions.append(
                {
                    "organization_id": organization_id,
                    "submission_version_id": submission_version_id,
                }
            )

            return DatabaseLoadedSubmissionVersion(
                organization_id=organization_id,
                submission_version_id=submission_version_id,
                submission_id=submission_id,
                version_number=1,
                content_text=content_text,
            )

    monkeypatch.setattr(
        "app.services.analysis_worker_factory."
        "DatabaseSubmissionVersionLoader",
        StubSubmissionVersionLoader,
    )

    repositories = []

    def make_repository(_session):
        repository = FakeAnalysisJobRepository(job)
        repositories.append(repository)
        return repository

    monkeypatch.setattr(
        "app.services.analysis_worker_service.AnalysisJobRepository",
        make_repository,
    )

    session = FakeSession()
    queue = Mock()

    # No live AI service is used by this deterministic integration test.
    with patch(
        "app.services.analysis_pipeline_factory.get_settings",
        return_value=SimpleNamespace(ai_provider="disabled"),
    ):
        worker = build_analysis_worker_service(
            session,
            queue,
        )
        result = worker.process_job(job_id)

    assert loaded_versions == [
        {
            "organization_id": organization_id,
            "submission_version_id": submission_version_id,
        }
    ]

    knowledge_loader.load.assert_called_once_with(
        organization_id=organization_id,
    )

    assert len(repositories) == 1
    persisted = repositories[0].persisted
    assert persisted is not None

    assert persisted["organization_id"] == organization_id
    assert persisted["job_id"] == job_id
    assert persisted["submission_version_id"] == submission_version_id
    assert persisted["claimed_attempt"] == 1

    # The deterministic factual check ran, but AI-only checks were disabled.
    assert persisted["final_status"] == "completed"
    assert persisted["submission_status"] == "under_review"

    findings = persisted["findings"]
    assert len(findings) == 1

    finding = findings[0]
    assert finding["category"] == "factual_claim"
    assert finding["severity"] == "medium"
    assert finding["result"] == "conflict"
    assert finding["source_fact_version_id"] == fact_version_id
    assert finding["evidence"]["submitted_text"] == "₹999"
    assert (
        finding["evidence"]["approved_reference"]
        == approved_fact.fact_text
    )
    assert finding["evidence"]["source_url"] == approved_fact.source_url
    assert finding["suggested_correction"] == "The price is ₹1299."
    assert finding["detection_method"] == "deterministic"
    assert finding["requires_human_review"] is True
    assert finding["finding_fingerprint"]

    assert job.status == "completed"
    assert session.commits >= 2
    assert session.rollbacks == 0
    queue.enqueue_analysis.assert_not_called()

    assert result is not None
    assert result.status == "completed"
    assert result.finding_count == 1
