from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DatasetORM(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(64), nullable=False)
    task_spec: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    embed_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ls_project_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SampleORM(Base):
    __tablename__ = "samples"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    image_uris: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    ls_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class OrganizationORM(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class OrgMembershipORM(Base):
    __tablename__ = "org_memberships"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (UniqueConstraint("user_id", "org_id"),)


class AnnotationORM(Base):
    __tablename__ = "annotations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sample_id: Mapped[str] = mapped_column(ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class TrainingPresetORM(Base):
    __tablename__ = "training_presets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_spec: Mapped[dict] = mapped_column(JSON, nullable=False)
    omegaconf_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    dataloader_ref: Mapped[str] = mapped_column(String(255), nullable=False)


class TrainingJobORM(Base):
    __tablename__ = "training_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False)
    preset_id: Mapped[str] = mapped_column(ForeignKey("training_presets.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    external_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class TrainingEventORM(Base):
    __tablename__ = "training_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("training_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class JobUserStateORM(Base):
    __tablename__ = "job_user_state"

    job_id: Mapped[str] = mapped_column(ForeignKey("training_jobs.id", ondelete="CASCADE"), primary_key=True)
    user_left: Mapped[bool] = mapped_column(default=False, nullable=False)


class ArtifactORM(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("training_jobs.id", ondelete="CASCADE"), nullable=False)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class PredictionORM(Base):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    result_type: Mapped[str] = mapped_column(String(64), nullable=False)
    sample_id: Mapped[str] = mapped_column(ForeignKey("samples.id", ondelete="CASCADE"), nullable=False)
    predicted_label: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    model_artifact_id: Mapped[str] = mapped_column(String(64), nullable=False)


class PredictionEditORM(Base):
    __tablename__ = "prediction_edits"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    result_id: Mapped[str] = mapped_column(ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False)
    corrected_label: Mapped[str] = mapped_column(String(255), nullable=False)
    edited_by: Mapped[str] = mapped_column(String(255), nullable=False)
    edited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class SampleFeatureORM(Base):
    __tablename__ = "sample_features"

    sample_id: Mapped[str] = mapped_column(ForeignKey("samples.id", ondelete="CASCADE"), primary_key=True)
    embedding: Mapped[list[float]] = mapped_column(JSON, default=list, nullable=False)
    embed_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
