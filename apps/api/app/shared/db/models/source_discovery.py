from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
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


class SourceConnectorORM(Base):
    __tablename__ = "source_connectors"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_source_connectors_org_name"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class SourceImportProfileVersionORM(Base):
    __tablename__ = "source_import_profile_versions"
    __table_args__ = (
        UniqueConstraint(
            "profile_key", "version", name="uq_source_import_profile_version"
        ),
        CheckConstraint("version > 0", name="ck_source_import_profile_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    connector_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_connectors.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CollectionMembershipRuleORM(Base):
    __tablename__ = "collection_membership_rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    collection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("dataset_collections.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    active_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    live_cursor: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CollectionMembershipRuleVersionORM(Base):
    __tablename__ = "collection_membership_rule_versions"
    __table_args__ = (
        UniqueConstraint(
            "rule_id", "version", name="uq_collection_membership_rule_version"
        ),
        CheckConstraint("version > 0", name="ck_collection_membership_rule_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rule_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("collection_membership_rules.id", ondelete="CASCADE"),
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    connector_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_connectors.id", ondelete="RESTRICT")
    )
    import_profile_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("source_import_profile_versions.id", ondelete="RESTRICT"),
    )
    condition: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ScAutomationPartitionORM(Base):
    __tablename__ = "sc_automation_partitions"
    __table_args__ = (
        UniqueConstraint("rule_id", name="uq_sc_automation_partitions_rule"),
        UniqueConstraint(
            "org_id",
            "connector_id",
            "partition_key",
            name="uq_sc_automation_partition_assignment",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    collection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("dataset_collections.id", ondelete="CASCADE"),
        index=True,
    )
    rule_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("collection_membership_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    connector_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_connectors.id", ondelete="RESTRICT")
    )
    layer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    device: Mapped[str] = mapped_column(String(255), nullable=False)
    partition_key: Mapped[str] = mapped_column(String(640), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CollectionDiscoveryRunORM(Base):
    __tablename__ = "collection_discovery_runs"
    __table_args__ = (
        Index(
            "ux_collection_discovery_runs_active_rule",
            "rule_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    collection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("dataset_collections.id", ondelete="CASCADE"),
        index=True,
    )
    rule_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("collection_membership_rules.id", ondelete="CASCADE"),
        index=True,
    )
    rule_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("collection_membership_rule_versions.id", ondelete="RESTRICT"),
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    range_start_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    range_end_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    timezone_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parent_run_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("collection_discovery_runs.id", ondelete="SET NULL")
    )
    collection_revision_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("dataset_collection_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    stats: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CollectionDiscoveryRunItemORM(Base):
    __tablename__ = "collection_discovery_run_items"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "source_record_key", name="uq_discovery_run_source_record"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("collection_discovery_runs.id", ondelete="CASCADE"),
        index=True,
    )
    connector_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_connectors.id", ondelete="RESTRICT")
    )
    source_record_key: Mapped[str] = mapped_column(String(512), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True
    )
    member_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("dataset_collection_members.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CollectionImportReceiptORM(Base):
    __tablename__ = "collection_import_receipts"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "connector_id",
            "source_record_key",
            "import_profile_version_id",
            name="uq_collection_import_identity",
        ),
        CheckConstraint("attempts > 0", name="ck_collection_import_attempts"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    collection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("dataset_collections.id", ondelete="CASCADE"),
        index=True,
    )
    connector_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_connectors.id", ondelete="RESTRICT")
    )
    source_record_key: Mapped[str] = mapped_column(String(512), nullable=False)
    import_profile_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("source_import_profile_versions.id", ondelete="RESTRICT"),
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CollectionDiscoveryReceiptORM(Base):
    __tablename__ = "collection_discovery_receipts"
    __table_args__ = (
        UniqueConstraint(
            "rule_id",
            "connector_id",
            "source_record_key",
            "import_profile_version_id",
            name="uq_collection_discovery_receipt",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    collection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("dataset_collections.id", ondelete="CASCADE"),
        index=True,
    )
    rule_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("collection_membership_rules.id", ondelete="CASCADE")
    )
    connector_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_connectors.id", ondelete="RESTRICT")
    )
    source_record_key: Mapped[str] = mapped_column(String(512), nullable=False)
    import_profile_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("source_import_profile_versions.id", ondelete="RESTRICT"),
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True
    )
    member_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("dataset_collection_members.id", ondelete="SET NULL"),
        nullable=True,
    )
    first_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("collection_discovery_runs.id", ondelete="CASCADE")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CollectionSourceMembershipORM(Base):
    __tablename__ = "collection_source_memberships"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "connector_id",
            "source_record_key",
            name="uq_collection_source_membership",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    collection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("dataset_collections.id", ondelete="CASCADE"),
        index=True,
    )
    connector_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_connectors.id", ondelete="RESTRICT")
    )
    source_record_key: Mapped[str] = mapped_column(String(512), nullable=False)
    dataset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("datasets.id", ondelete="RESTRICT")
    )
    member_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("dataset_collection_members.id", ondelete="CASCADE")
    )
    admitted_by_rule_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("collection_membership_rules.id", ondelete="RESTRICT")
    )
    admitted_by_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("collection_discovery_runs.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
