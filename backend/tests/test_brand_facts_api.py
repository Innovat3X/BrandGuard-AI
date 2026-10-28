import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.infrastructure.db.repositories.organization_membership_repository import (
    OrganizationMembershipRepository,
)
from app.infrastructure.db.session import get_db
from app.main import app

TEST_SECRET = "brand-facts-api-test-secret-123456789"


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


def register_user(
    client: TestClient,
    email: str = "facts-test@example.test",
) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Brand Facts Test User",
            "email": email,
            "password": "facts-test-password",
            "organization_name": "Facts Test Organisation",
        },
    )

    assert response.status_code == 201
    return response.json()


def auth_headers(auth_data: dict) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {auth_data['access_token']}",
    }


def structured_price_payload() -> dict:
    return {
        "label": "Product price",
        "fact_text": "The approved product price is ₹1299.",
        "source_url": "https://example.com/product",
        "fact_key": "product_price",
        "structured_value": {
            "kind": "currency",
            "value": "1299",
            "unit": "INR",
        },
    }


def test_create_structured_fact_and_list_it(client: TestClient):
    auth = register_user(client)

    create_response = client.post(
        "/api/v1/brand/facts",
        json=structured_price_payload(),
        headers=auth_headers(auth),
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["label"] == "Product price"
    assert len(created["versions"]) == 1

    version = created["versions"][0]
    assert version["status"] == "draft"
    assert version["fact_key"] == "product_price"
    assert version["structured_value"] == {
        "kind": "currency",
        "value": "1299",
        "unit": "INR",
    }

    list_response = client.get(
        "/api/v1/brand/facts",
        headers=auth_headers(auth),
    )

    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == created["id"]
    assert items[0]["versions"][0]["fact_key"] == "product_price"


def test_create_legacy_free_text_fact(client: TestClient):
    auth = register_user(client)

    response = client.post(
        "/api/v1/brand/facts",
        json={
            "label": "Product description",
            "fact_text": "The product comes in three sizes.",
        },
        headers=auth_headers(auth),
    )

    assert response.status_code == 201
    version = response.json()["versions"][0]
    assert version["status"] == "draft"
    assert version["fact_key"] is None
    assert version["structured_value"] is None


def test_create_fact_rejects_invalid_structured_unit(client: TestClient):
    auth = register_user(client)

    payload = structured_price_payload()
    payload["structured_value"]["unit"] = "JPY"

    response = client.post(
        "/api/v1/brand/facts",
        json=payload,
        headers=auth_headers(auth),
    )

    assert response.status_code == 422


def test_create_fact_requires_structured_fields_together(
    client: TestClient,
):
    auth = register_user(client)

    payload = structured_price_payload()
    payload.pop("structured_value")

    response = client.post(
        "/api/v1/brand/facts",
        json=payload,
        headers=auth_headers(auth),
    )

    assert response.status_code == 422


def test_brand_facts_require_authentication(client: TestClient):
    response = client.get("/api/v1/brand/facts")
    assert response.status_code == 401

    response = client.post(
        "/api/v1/brand/facts",
        json=structured_price_payload(),
    )
    assert response.status_code == 401


def test_reviewer_cannot_create_fact(
    client: TestClient,
    db_session: Session,
):
    auth = register_user(client)

    membership = OrganizationMembershipRepository(
        db_session
    ).get_membership(
        organization_id=auth["organization"]["id"],
        user_id=auth["user"]["id"],
    )

    assert membership is not None
    membership.role = "reviewer"
    db_session.flush()

    response = client.post(
        "/api/v1/brand/facts",
        json=structured_price_payload(),
        headers=auth_headers(auth),
    )

    assert response.status_code == 403


def test_admin_can_approve_structured_fact(client: TestClient):
    auth = register_user(client)

    create_response = client.post(
        "/api/v1/brand/facts",
        json=structured_price_payload(),
        headers=auth_headers(auth),
    )

    assert create_response.status_code == 201
    created = create_response.json()

    response = client.post(
        f"/api/v1/brand/facts/{created['id']}/approve",
        headers=auth_headers(auth),
    )

    assert response.status_code == 200
    approved = response.json()
    version = approved["versions"][0]

    assert version["status"] == "approved"
    assert version["approved_by"] == auth["user"]["id"]
    assert version["approved_at"] is not None
    assert version["structured_value"]["value"] == "1299"


def test_other_organisation_cannot_approve_fact(client: TestClient):
    owner = register_user(
        client,
        email="facts-owner@example.test",
    )

    create_response = client.post(
        "/api/v1/brand/facts",
        json=structured_price_payload(),
        headers=auth_headers(owner),
    )

    assert create_response.status_code == 201
    fact_id = create_response.json()["id"]

    other_user = register_user(
        client,
        email="facts-other@example.test",
    )

    response = client.post(
        f"/api/v1/brand/facts/{fact_id}/approve",
        headers=auth_headers(other_user),
    )

    assert response.status_code == 404