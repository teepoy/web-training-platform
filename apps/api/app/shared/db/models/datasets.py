from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DatasetORM(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(64), nullable=False)
    task_spec: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    embed_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ls_project_id: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_mode: Mapped[str] = mapped_column(
        String(64), nullable=False, default="db_full", server_default="db_full"
    )


class SampleORM(Base):
    __tablename__ = "samples"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    image_uris: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    ls_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class AnnotationORM(Base):
    __tablename__ = "annotations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sample_id: Mapped[str] = mapped_column(
        ForeignKey("samples.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    annotation_value: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class SampleFeatureORM(Base):
    __tablename__ = "sample_features"

    sample_id: Mapped[str] = mapped_column(
        ForeignKey("samples.id", ondelete="CASCADE"), primary_key=True
    )
    embedding: Mapped[list[float]] = mapped_column(JSON, default=list, nullable=False)
    embed_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AnnotationVersionORM(Base):
    __tablename__ = "annotation_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    review_action_id: Mapped[str] = mapped_column(
        ForeignKey("prediction_review_actions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    annotation_id: Mapped[str] = mapped_column(
        ForeignKey("annotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    prediction_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("platform_predictions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    predicted_label: Mapped[str] = mapped_column(String(255), nullable=False)
    final_label: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
