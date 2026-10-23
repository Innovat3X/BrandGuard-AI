import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.brand_asset import BrandAsset


class BrandAssetRepository:
    """Persistence operations for brand asset metadata.

    Original file bytes belong in private file storage, not PostgreSQL.
    The application service owns transactions, commits, permissions,
    upload validation, and asset-approval workflow decisions.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_asset(
        self,
        organization_id: UUID,
        name: str,
        asset_type: str,
        storage_key: str,
        media_type: str,
        size_bytes: int,
        checksum_sha256: str,
        status: str,
        created_by: UUID,
        metadata: dict[str, Any] | None = None,
    ) -> BrandAsset:
        """Persist asset metadata and its private storage reference.

        Status is required, but its allowed values must be agreed by the
        team before a repository-level status constraint is introduced.
        """
        self._validate_required_text("Asset name", name)
        self._validate_required_text("Asset type", asset_type)
        self._validate_required_text("Storage key", storage_key)
        self._validate_required_text("Media type", media_type)
        self._validate_required_text("Asset status", status)

        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int):
            raise ValueError("Asset size must be an integer.")

        if size_bytes < 0:
            raise ValueError("Asset size cannot be negative.")

        if not re.fullmatch(r"[0-9a-fA-F]{64}", checksum_sha256):
            raise ValueError(
                "SHA-256 checksum must contain exactly 64 hexadecimal characters."
            )

        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("Asset metadata must be a dictionary or None.")

        asset = BrandAsset(
            organization_id=organization_id,
            name=name.strip(),
            asset_type=asset_type.strip(),
            storage_key=storage_key,
            media_type=media_type.strip(),
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256.lower(),
            status=status.strip(),
            created_by=created_by,
            metadata_json=metadata,
        )

        self._session.add(asset)
        self._session.flush()

        return asset

    def get_asset(
        self,
        organization_id: UUID,
        asset_id: UUID,
    ) -> BrandAsset | None:
        """Retrieve asset metadata within the specified organization."""
        statement = select(BrandAsset).where(
            BrandAsset.organization_id == organization_id,
            BrandAsset.id == asset_id,
        )

        return self._session.scalar(statement)

    def list_assets(
        self,
        organization_id: UUID,
        asset_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[BrandAsset]:
        """List organization-scoped assets with optional filters."""
        if limit < 1:
            raise ValueError("Limit must be at least 1.")

        statement = select(BrandAsset).where(
            BrandAsset.organization_id == organization_id
        )

        if asset_type is not None:
            self._validate_required_text("Asset type", asset_type)
            statement = statement.where(
                BrandAsset.asset_type == asset_type.strip()
            )

        if status is not None:
            self._validate_required_text("Asset status", status)
            statement = statement.where(BrandAsset.status == status.strip())

        statement = (
            statement
            .order_by(BrandAsset.created_at.desc(), BrandAsset.id)
            .limit(limit)
        )

        return list(self._session.scalars(statement).all())

    @staticmethod
    def _validate_required_text(field_name: str, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must not be empty.")