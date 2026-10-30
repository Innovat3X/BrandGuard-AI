
"""Integration test for worker execution with the real analysis pipeline."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.infrastructure.db.analysis_knowledge_loader import (
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
    """Track transaction boundaries without opening a database."""

    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeAnalysisJobRepository:
    """Capture worker persistence calls for this integration test."""

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


def test_worker_runs_real_analysis_and_hands_findings_to_persistence(
    monkeypatch,
):
    organization_id = uuid4()
    job_id = uuid4()
    submission_id = uuid4()
    submission_version_id = uuid4()
    rule_version_id = uuid4()

    content_text = "Our cheap product is available today."

    job = SimpleNamespace(
        id=job_id,
        organization_id=organization_id,
        submission_version_id=submission_version_id,
        requested_checks=None,
        status="queued",
        attempts=0,
    )

    rule = ApprovedRuleVersionRecord(
        organization_id=organization_id,
        rule_id=uuid4(),
        version_id=rule_version_id,
        version_number=1,
        category="terminology",
        rule_text="forbidden_term: cheap",
        severity="medium",
        approved_by=uuid4(),
        approved_at=APPROVED_AT,
        effective_from=None,
    )

    knowledge = SimpleNamespace(
        organization_id=organization_id,
        as_of=APPROVED_AT,
        rule_versions=(rule,),
        fact_versions=(),
    )

    knowledge_loader = Mock()
    knowledge_loader.load.return_value = knowledge

    def build_fake_knowledge_loader(_session, **_kwargs):
        """Accept the same constructor arguments as the real loader."""
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

    worker = build_analysis_worker_service(
        session,
        queue,
        claim_extractor=lambda _text: [],
    )

    result = worker.process_job(job_id)

    assert len(loaded_versions) == 1
    assert loaded_versions[0] == {
        "organization_id": organization_id,
        "submission_version_id": submission_version_id,
    }

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
    assert persisted["final_status"] == "partial"
    assert persisted["submission_status"] == "under_review"

    findings = persisted["findings"]
    assert len(findings) == 1

    check_outcomes = persisted["check_outcomes"]
    assert isinstance(check_outcomes, list)
    assert check_outcomes
    assert all(
        {"category", "status", "message"}.issubset(outcome)
        for outcome in check_outcomes
    )

    finding = findings[0]
    assert finding["category"] == "terminology"
    assert finding["severity"] == "medium"
    assert finding["result"] == "conflict"
    assert finding["source_rule_version_id"] == rule_version_id
    assert finding["finding_fingerprint"]

    # WorkerResult exposes the job outcome, not check_outcomes.
    assert result is not None
    assert result.status == "partial"
    assert result.finding_count == 1
    assert result.attempts == 1

    assert job.status == "partial"
    assert session.commits >= 2
    assert session.rollbacks == 0
    queue.enqueue_analysis.assert_not_called()
