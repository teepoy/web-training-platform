from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ScheduleORM(Base):
    __tablename__ = "schedules"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid4())
    )
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    prefect_deployment_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    flow_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cron: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_schedule_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
