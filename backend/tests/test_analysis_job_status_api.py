from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.infrastructure.db.repositories.analysis_job_repository import (
    AnalysisJobRepository,
)
from app.infrastructure.db.repositories.submission_repository import (
    SubmissionRepository,
)
from app.infrastructure.db.session import get_db
from app.main import app


TEST_SECRET = "analysis-job-api-test-secret-123456789"


@pytest.fixture
def client(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    get_settings.cache_clear()

    original_overrides = app.dependency_overrides.copy()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        get_settings.cache_clear()


def register_user(client: TestClient, email: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Analysis Status Test User",
            "email": email,
            "password": "analysis-status-test-password",
            "organization_name": f"Organisation {email}",
        },
    )
    assert response.status_code == 201
    return response.json()


def auth_headers(auth: dict) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {auth['access_token']}",
    }


def test_analysis_job_status_returns_persisted_check_outcomes(
    client: TestClient,
    db_session: Session,
):
    owner = register_user(
        client,
        "analysis-status-owner@example.test",
    )
    organization_id = UUID(owner["organization"]["id"])

    submission_response = client.post(
        "/api/v1/submissions",
        data={
            "title": "Analysis status API test",
            "text": "Our product uses the approved brand terminology.",
        },
        headers=auth_headers(owner),
    )
    assert submission_response.status_code == 201

    submission_id = UUID(
        submission_response.json()["submission_id"]
    )

    version = SubmissionRepository(
        db_session
    ).get_submission_version(
        organization_id=organization_id,
        submission_id=submission_id,
        version_number=1,
    )
    assert version is not None

    job = AnalysisJobRepository(
        db_session
    ).create_or_get_analysis_job(
        organization_id=organization_id,
        submission_version_id=version.id,
        idempotency_key="analysis-status-api-check-outcomes",
    )

    expected_outcomes = [
        {
            "category": "terminology",
            "status": "disabled",
            "message": "Terminology checking was not requested.",
            "detection_method": None,
            "assessed_count": 0,
            "scope": None,
        },
        {
            "category": "factual_claim",
            "status": "supported",
            "message": "Factual claim checks completed.",
            "detection_method": "deterministic",
            "assessed_count": 1,
            "scope": "submitted_text",
        },
    ]

    job.check_outcomes = expected_outcomes
    db_session.flush()

    response = client.get(
        f"/api/v1/analysis-jobs/{job.id}",
        headers=auth_headers(owner),
    )

    assert response.status_code == 200
    body = response.json()

    assert body["job_id"] == str(job.id)
    assert body["submission_id"] == str(submission_id)
    assert body["version_number"] == 1
    assert body["check_outcomes"] == expected_outcomes

    # A different organisation must not be able to read this job.
    other_user = register_user(
        client,
        "analysis-status-other@example.test",
    )
    forbidden_response = client.get(
        f"/api/v1/analysis-jobs/{job.id}",
        headers=auth_headers(other_user),
    )
    assert forbidden_response.status_code == 404


def test_analysis_job_status_requires_authentication(
    client: TestClient,
):
    response = client.get(
        "/api/v1/analysis-jobs/00000000-0000-0000-0000-000000000001"
    )
    assert response.status_code == 401
