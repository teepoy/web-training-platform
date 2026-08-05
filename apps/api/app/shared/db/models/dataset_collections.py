from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DatasetCollectionORM(Base):
    __tablename__ = "dataset_collections"
    __table_args__ = (
        CheckConstraint(
            "definition_version >= 0",
            name="ck_dataset_collections_definition_version_nonnegative",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_view_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_view_contract: Mapped[str] = mapped_column(String(255), nullable=False)
    target_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    duplicate_policy: Mapped[str] = mapped_column(String(64), nullable=False)
    missing_data_policy: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class DatasetCollectionMemberORM(Base):
    __tablename__ = "dataset_collection_members"
    __table_args__ = (
        CheckConstraint(
            "position >= 0",
            name="ck_dataset_collection_members_position_nonnegative",
        ),
        CheckConstraint(
            "linked_definition_version > 0",
            name="ck_dataset_collection_members_linked_version_positive",
        ),
        CheckConstraint(
            "unlinked_definition_version IS NULL OR "
            "unlinked_definition_version > linked_definition_version",
            name="ck_dataset_collection_members_version_interval",
        ),
        CheckConstraint(
            "unlinked_at IS NOT NULL OR source_dataset_id IS NOT NULL",
            name="ck_dataset_collection_members_active_source_present",
        ),
        Index(
            "uq_dataset_collection_members_active_dataset",
            "collection_id",
            "source_dataset_id",
            unique=True,
            sqlite_where=text("unlinked_at IS NULL"),
            postgresql_where=text("unlinked_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    collection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("dataset_collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_dataset_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_dataset_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    linked_definition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    unlinked_definition_version: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    filter_spec: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    label_mapping: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sampling_spec: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    linked_by: Mapped[str] = mapped_column(String(255), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    unlinked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unlinked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class DatasetCollectionRevisionORM(Base):
    __tablename__ = "dataset_collection_revisions"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "revision_number",
            name="uq_dataset_collection_revisions_number",
        ),
        CheckConstraint(
            "revision_number > 0",
            name="ck_dataset_collection_revisions_number_positive",
        ),
        CheckConstraint(
            "definition_version > 0",
            name="ck_dataset_collection_revisions_definition_version_positive",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    collection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("dataset_collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    target_view_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_view_contract: Mapped[str] = mapped_column(String(255), nullable=False)
    target_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_snapshot: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    manifest_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
