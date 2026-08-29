from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SimulatorClockORM(Base):
    __tablename__ = "simulator_clock"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_simulator_clock_singleton"),
        CheckConstraint(
            "next_change_token > 0", name="ck_simulator_clock_positive_token"
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    next_change_token: Mapped[int] = mapped_column(BigInteger, nullable=False)


class InspectionORM(Base):
    __tablename__ = "simulator_inspections"
    __table_args__ = (
        CheckConstraint(
            "state IN ('draft', 'published')", name="ck_simulator_inspection_state"
        ),
        CheckConstraint(
            "(state = 'draft' AND published_at IS NULL AND last_updated_at IS NULL "
            "AND change_token IS NULL) OR "
            "(state = 'published' AND published_at IS NOT NULL "
            "AND last_updated_at IS NOT NULL AND change_token IS NOT NULL)",
            name="ck_simulator_inspection_publication_fields",
        ),
        UniqueConstraint("change_token", name="uq_simulator_inspection_change_token"),
        Index("ix_simulator_inspections_published_time", "state", "inspection_time"),
    )

    wafer_key: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    inspection_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    lot_id: Mapped[str] = mapped_column(String(50), nullable=False)
    wafer_id: Mapped[str] = mapped_column(String(50), nullable=False)
    layer_id: Mapped[str] = mapped_column(String(50), nullable=False)
    device: Mapped[str] = mapped_column(String(50), nullable=False)
    inspect_equip_id: Mapped[str] = mapped_column(String(50), nullable=False)
    recipe_key: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recipe_id: Mapped[str] = mapped_column(String(50), nullable=False)
    origin_index_x: Mapped[int] = mapped_column(Integer, nullable=False)
    origin_index_y: Mapped[int] = mapped_column(Integer, nullable=False)
    center_x: Mapped[int] = mapped_column(Integer, nullable=False)
    center_y: Mapped[int] = mapped_column(Integer, nullable=False)
    origin_x: Mapped[int] = mapped_column(Integer, nullable=False)
    origin_y: Mapped[int] = mapped_column(Integer, nullable=False)
    die_size_x: Mapped[int] = mapped_column(Integer, nullable=False)
    die_size_y: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    change_token: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class DefectORM(Base):
    __tablename__ = "simulator_defects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["wafer_key", "inspection_time"],
            [
                "simulator_inspections.wafer_key",
                "simulator_inspections.inspection_time",
            ],
            ondelete="CASCADE",
        ),
    )

    wafer_key: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    inspection_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    defect_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    test_id: Mapped[int] = mapped_column(Integer, nullable=False)
    class_number: Mapped[int] = mapped_column(Integer, nullable=False)
    rough_bin: Mapped[int] = mapped_column(Integer, nullable=False)
    wafer_x: Mapped[int] = mapped_column(Integer, nullable=False)
    wafer_y: Mapped[int] = mapped_column(Integer, nullable=False)
    index_x: Mapped[int] = mapped_column(Integer, nullable=False)
    index_y: Mapped[int] = mapped_column(Integer, nullable=False)
    adder: Mapped[int] = mapped_column(Integer, nullable=False)
    cluster: Mapped[int] = mapped_column(Integer, nullable=False)
    images: Mapped[int] = mapped_column(Integer, nullable=False)
    size_x: Mapped[int] = mapped_column(Integer, nullable=False)
    size_y: Mapped[int] = mapped_column(Integer, nullable=False)
    size_d: Mapped[int] = mapped_column(Integer, nullable=False)
    area: Mapped[int] = mapped_column(Integer, nullable=False)
    final_bin: Mapped[int] = mapped_column(Integer, nullable=False)
    manual_bin: Mapped[int] = mapped_column(Integer, nullable=False)
    kill_ratio: Mapped[float] = mapped_column(Float, nullable=False)


class ReviewImageORM(Base):
    __tablename__ = "simulator_review_images"
    __table_args__ = (
        ForeignKeyConstraint(
            ["wafer_key", "inspection_time"],
            [
                "simulator_inspections.wafer_key",
                "simulator_inspections.inspection_time",
            ],
            ondelete="CASCADE",
        ),
    )

    wafer_key: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    inspection_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    defect_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    image_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    image_type: Mapped[str] = mapped_column(String(50), nullable=False)
    image_filespec: Mapped[str] = mapped_column(String(1024), nullable=False)


class PatchArchiveORM(Base):
    __tablename__ = "simulator_patch_archives"
    __table_args__ = (
        ForeignKeyConstraint(
            ["wafer_key", "inspection_time"],
            [
                "simulator_inspections.wafer_key",
                "simulator_inspections.inspection_time",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "wafer_key",
            "inspection_time",
            "s3_bucket",
            "s3_key",
            name="uq_simulator_patch_archive_object",
        ),
    )

    wafer_key: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    inspection_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    archive_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    s3_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
