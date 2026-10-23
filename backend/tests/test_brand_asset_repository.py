
from uuid import uuid4

import pytest

from app.infrastructure.db import Organization, User
from app.infrastructure.db.repositories.brand_asset_repository import (
    BrandAssetRepository,
)


def create_org_user(db_session):
    suffix = uuid4().hex

    organization = Organization(name=f"Test Organization {suffix}")
    user = User(
        full_name="Brand Asset Test User",
        email=f"{suffix}@example.com",
        password_hash="test-password-hash",
    )

    db_session.add_all([organization, user])
    db_session.flush()

    return organization, user


def create_asset(
    db_session,
    organization,
    user,
    *,
    name="Primary Logo",
    asset_type="logo",
    status="draft",
    checksum=None,
):
    repository = BrandAssetRepository(db_session)

    return repository.create_asset(
        organization_id=organization.id,
        name=name,
        asset_type=asset_type,
        storage_key=f"private/{uuid4().hex}.png",
        media_type="image/png",
        size_bytes=2048,
        checksum_sha256=checksum or ("a" * 64),
        status=status,
        created_by=user.id,
        metadata={"source": "test"},
    )


def test_create_asset_persists_metadata(db_session):
    organization, user = create_org_user(db_session)

    asset = create_asset(db_session, organization, user)

    assert asset.id is not None
    assert asset.organization_id == organization.id
    assert asset.name == "Primary Logo"
    assert asset.asset_type == "logo"
    assert asset.storage_key.startswith("private/")
    assert asset.media_type == "image/png"
    assert asset.size_bytes == 2048
    assert asset.checksum_sha256 == "a" * 64
    assert asset.status == "draft"
    assert asset.created_by == user.id
    assert asset.metadata_json == {"source": "test"}
    assert asset.approved_by is None
    assert asset.approved_at is None


def test_create_asset_normalizes_text_and_checksum(db_session):
    organization, user = create_org_user(db_session)
    repository = BrandAssetRepository(db_session)

    asset = repository.create_asset(
        organization_id=organization.id,
        name="  Brand Logo  ",
        asset_type="  logo  ",
        storage_key="private/logo.png",
        media_type="  image/png  ",
        size_bytes=100,
        checksum_sha256="A" * 64,
        status="  draft  ",
        created_by=user.id,
    )

    assert asset.name == "Brand Logo"
    assert asset.asset_type == "logo"
    assert asset.media_type == "image/png"
    assert asset.checksum_sha256 == "a" * 64
    assert asset.status == "draft"


def test_get_asset_is_organization_scoped(db_session):
    organization, user = create_org_user(db_session)
    asset = create_asset(db_session, organization, user)

    other_organization, _ = create_org_user(db_session)
    repository = BrandAssetRepository(db_session)

    assert repository.get_asset(organization.id, asset.id) is not None
    assert repository.get_asset(other_organization.id, asset.id) is None


def test_list_assets_is_organization_scoped(db_session):
    organization, user = create_org_user(db_session)
    asset = create_asset(db_session, organization, user)

    other_organization, other_user = create_org_user(db_session)
    other_asset = create_asset(
        db_session,
        other_organization,
        other_user,
        name="Other Logo",
    )

    repository = BrandAssetRepository(db_session)

    first_results = repository.list_assets(organization.id)
    second_results = repository.list_assets(other_organization.id)

    assert [item.id for item in first_results] == [asset.id]
    assert [item.id for item in second_results] == [other_asset.id]


def test_list_assets_supports_type_and_status_filters(db_session):
    organization, user = create_org_user(db_session)

    logo = create_asset(
        db_session,
        organization,
        user,
        name="Logo",
        asset_type="logo",
        status="approved",
    )
    create_asset(
        db_session,
        organization,
        user,
        name="Typography Guide",
        asset_type="document",
        status="draft",
    )

    repository = BrandAssetRepository(db_session)

    approved_logos = repository.list_assets(
        organization_id=organization.id,
        asset_type="logo",
        status="approved",
    )

    assert [item.id for item in approved_logos] == [logo.id]


def test_list_assets_returns_empty_list_when_no_match(db_session):
    organization, user = create_org_user(db_session)
    create_asset(
        db_session,
        organization,
        user,
        asset_type="logo",
    )

    repository = BrandAssetRepository(db_session)

    results = repository.list_assets(
        organization_id=organization.id,
        asset_type="document",
    )

    assert results == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", " "),
        ("asset_type", ""),
        ("storage_key", " "),
        ("media_type", ""),
        ("status", " "),
    ],
)
def test_create_asset_rejects_empty_required_text(
    db_session, field, value
):
    organization, user = create_org_user(db_session)
    repository = BrandAssetRepository(db_session)

    values = {
        "organization_id": organization.id,
        "name": "Logo",
        "asset_type": "logo",
        "storage_key": "private/logo.png",
        "media_type": "image/png",
        "size_bytes": 100,
        "checksum_sha256": "a" * 64,
        "status": "draft",
        "created_by": user.id,
    }
    values[field] = value

    with pytest.raises(ValueError):
        repository.create_asset(**values)


@pytest.mark.parametrize("size_bytes", [-1, True, 1.5])
def test_create_asset_rejects_invalid_size(db_session, size_bytes):
    organization, user = create_org_user(db_session)
    repository = BrandAssetRepository(db_session)

    with pytest.raises(ValueError):
        repository.create_asset(
            organization_id=organization.id,
            name="Logo",
            asset_type="logo",
            storage_key="private/logo.png",
            media_type="image/png",
            size_bytes=size_bytes,
            checksum_sha256="a" * 64,
            status="draft",
            created_by=user.id,
        )


@pytest.mark.parametrize(
    "checksum",
    [
        "",
        "a" * 63,
        "g" * 64,
        "a" * 65,
    ],
)
def test_create_asset_rejects_invalid_checksum(db_session, checksum):
    organization, user = create_org_user(db_session)
    repository = BrandAssetRepository(db_session)

    with pytest.raises(ValueError, match="SHA-256"):
        repository.create_asset(
            organization_id=organization.id,
            name="Logo",
            asset_type="logo",
            storage_key="private/logo.png",
            media_type="image/png",
            size_bytes=100,
            checksum_sha256=checksum,
            status="draft",
            created_by=user.id,
        )


def test_create_asset_rejects_non_dictionary_metadata(db_session):
    organization, user = create_org_user(db_session)
    repository = BrandAssetRepository(db_session)

    with pytest.raises(ValueError, match="metadata"):
        repository.create_asset(
            organization_id=organization.id,
            name="Logo",
            asset_type="logo",
            storage_key="private/logo.png",
            media_type="image/png",
            size_bytes=100,
            checksum_sha256="a" * 64,
            status="draft",
            created_by=user.id,
            metadata=["not", "a", "dictionary"],
        )


@pytest.mark.parametrize("limit", [0, -1])
def test_list_assets_rejects_invalid_limit(db_session, limit):
    organization, _ = create_org_user(db_session)
    repository = BrandAssetRepository(db_session)

    with pytest.raises(ValueError, match="at least 1"):
        repository.list_assets(organization.id, limit=limit)


def test_asset_status_values_are_not_hardcoded(db_session):
    organization, user = create_org_user(db_session)

    # The contract has not finalized the permitted asset status values.
    asset = create_asset(
        db_session,
        organization,
        user,
        status="pending_team_review",
    )

    assert asset.status == "pending_team_review"
