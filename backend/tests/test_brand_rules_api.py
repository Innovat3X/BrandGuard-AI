import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.infrastructure.db.repositories.organization_membership_repository import (
    OrganizationMembershipRepository,
)
from app.infrastructure.db.session import get_db
from app.main import app

TEST_SECRET = "brand-rules-api-test-secret-123456789"


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
            "full_name": "Brand Rules Test User",
            "email": email,
            "password": "rules-test-password",
            "organization_name": f"Organisation {email}",
        },
    )
    assert response.status_code == 201
    return response.json()


def auth_headers(auth_data: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_data['access_token']}"}


def rule_payload() -> dict:
    return {
        "title": "Approved terminology",
        "category": "terminology",
        "description": "Terminology requirement",
        "rule_text": "forbidden_term: cheap",
        "severity": "medium",
    }


def test_create_and_list_brand_rules(client: TestClient):
    auth = register_user(client, "rules-create@example.test")
    headers = auth_headers(auth)

    created_response = client.post(
        "/api/v1/brand/rules",
        json=rule_payload(),
        headers=headers,
    )
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["title"] == "Approved terminology"
    assert len(created["versions"]) == 1
    assert created["versions"][0]["status"] == "draft"
    assert created["versions"][0]["rule_text"] == "forbidden_term: cheap"

    listed_response = client.get("/api/v1/brand/rules", headers=headers)
    assert listed_response.status_code == 200
    items = listed_response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == created["id"]
    assert items[0]["versions"][0]["version_number"] == 1


def test_brand_rules_require_authentication(client: TestClient):
    assert client.get("/api/v1/brand/rules").status_code == 401
    assert client.post(
        "/api/v1/brand/rules",
        json=rule_payload(),
    ).status_code == 401


def test_create_rule_rejects_invalid_category(client: TestClient):
    auth = register_user(client, "rules-invalid@example.test")
    payload = rule_payload()
    payload["category"] = "visual"
    response = client.post(
        "/api/v1/brand/rules",
        json=payload,
        headers=auth_headers(auth),
    )
    assert response.status_code == 422


def test_update_latest_draft_rule(client: TestClient):
    auth = register_user(client, "rules-update@example.test")
    headers = auth_headers(auth)
    created = client.post(
        "/api/v1/brand/rules",
        json=rule_payload(),
        headers=headers,
    ).json()

    payload = {
        "title": "Updated terminology",
        "category": "terminology",
        "description": "Updated description",
        "rule_text": "forbidden_term: bargain",
        "severity": "high",
    }
    response = client.put(
        f"/api/v1/brand/rules/{created['id']}",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "Updated terminology"
    assert len(updated["versions"]) == 1
    assert updated["versions"][0]["version_number"] == 1
    assert updated["versions"][0]["rule_text"] == "forbidden_term: bargain"
    assert updated["versions"][0]["severity"] == "high"


def test_approved_rule_requires_new_version_before_update(client: TestClient):
    auth = register_user(client, "rules-approved-update@example.test")
    headers = auth_headers(auth)
    created = client.post(
        "/api/v1/brand/rules",
        json=rule_payload(),
        headers=headers,
    ).json()
    rule_id = created["id"]

    approved = client.post(
        f"/api/v1/brand/rules/{rule_id}/approve",
        headers=headers,
    )
    assert approved.status_code == 200

    update_response = client.put(
        f"/api/v1/brand/rules/{rule_id}",
        json=rule_payload(),
        headers=headers,
    )
    assert update_response.status_code == 409


def test_cannot_create_another_version_while_draft_is_pending(
    client: TestClient,
):
    auth = register_user(client, "rules-pending-draft@example.test")
    headers = auth_headers(auth)
    created = client.post(
        "/api/v1/brand/rules",
        json=rule_payload(),
        headers=headers,
    ).json()

    response = client.post(
        f"/api/v1/brand/rules/{created['id']}/versions",
        json={
            "category": "terminology",
            "rule_text": "forbidden_term: bargain",
            "severity": "medium",
        },
        headers=headers,
    )
    assert response.status_code == 409


def test_create_new_version_and_approve(client: TestClient):
    auth = register_user(client, "rules-version@example.test")
    headers = auth_headers(auth)
    created = client.post(
        "/api/v1/brand/rules",
        json=rule_payload(),
        headers=headers,
    ).json()
    rule_id = created["id"]

    first_approval = client.post(
        f"/api/v1/brand/rules/{rule_id}/approve",
        headers=headers,
    )
    assert first_approval.status_code == 200

    new_version_payload = {
        "category": "terminology",
        "description": "Second version",
        "rule_text": "forbidden_term: cheapest",
        "severity": "high",
    }
    version_response = client.post(
        f"/api/v1/brand/rules/{rule_id}/versions",
        json=new_version_payload,
        headers=headers,
    )
    assert version_response.status_code == 201
    versions = version_response.json()["versions"]
    assert [item["version_number"] for item in versions] == [1, 2]
    assert versions[0]["status"] == "approved"
    assert versions[1]["status"] == "draft"

    second_approval = client.post(
        f"/api/v1/brand/rules/{rule_id}/approve",
        headers=headers,
    )
    assert second_approval.status_code == 200
    approved_versions = second_approval.json()["versions"]
    assert approved_versions[0]["status"] == "approved"
    assert approved_versions[1]["status"] == "approved"
    assert approved_versions[1]["approved_at"] is not None


def test_other_organisation_cannot_see_or_approve_rule(client: TestClient):
    owner = register_user(client, "rules-owner@example.test")
    other = register_user(client, "rules-other@example.test")
    created = client.post(
        "/api/v1/brand/rules",
        json=rule_payload(),
        headers=auth_headers(owner),
    ).json()

    other_list = client.get(
        "/api/v1/brand/rules",
        headers=auth_headers(other),
    )
    assert other_list.status_code == 200
    assert other_list.json()["items"] == []

    approve_response = client.post(
        f"/api/v1/brand/rules/{created['id']}/approve",
        headers=auth_headers(other),
    )
    assert approve_response.status_code == 404


def test_reviewer_can_approve_but_cannot_create_rule(
    client: TestClient,
    db_session: Session,
):
    auth = register_user(client, "rules-reviewer@example.test")
    membership = OrganizationMembershipRepository(db_session).get_membership(
        organization_id=auth["organization"]["id"],
        user_id=auth["user"]["id"],
    )
    assert membership is not None
    membership.role = "reviewer"
    db_session.flush()
    headers = auth_headers(auth)

    create_response = client.post(
        "/api/v1/brand/rules",
        json=rule_payload(),
        headers=headers,
    )
    assert create_response.status_code == 403

    # Create as admin first, then exercise reviewer approval permissions.
    membership.role = "admin"
    db_session.flush()
    created = client.post(
        "/api/v1/brand/rules",
        json=rule_payload(),
        headers=headers,
    ).json()
    membership.role = "reviewer"
    db_session.flush()

    approve_response = client.post(
        f"/api/v1/brand/rules/{created['id']}/approve",
        headers=headers,
    )
    assert approve_response.status_code == 200
