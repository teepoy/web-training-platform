from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, foreign, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class BaseZips(DeclarativeBase):
    pass


class InspWaferSummaryORM(Base):
    __tablename__ = "insp_wafer_summary"

    wafer_key: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspection_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    lot_id: Mapped[str] = mapped_column(String(50), nullable=False)
    wafer_id: Mapped[str] = mapped_column(String(50), nullable=False)
    layer_id: Mapped[str] = mapped_column(String(50), nullable=False)
    recipe_key: Mapped[int] = mapped_column(Integer, nullable=False)
    inspect_equip_id: Mapped[str] = mapped_column(String(50), nullable=False)
    last_update: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    defects: Mapped[int] = mapped_column(Integer, nullable=False)
    images: Mapped[int] = mapped_column(Integer, nullable=False)
    center_x: Mapped[int] = mapped_column(Integer, nullable=False)
    center_y: Mapped[int] = mapped_column(Integer, nullable=False)
    origin_x: Mapped[int] = mapped_column(Integer, nullable=False)
    origin_y: Mapped[int] = mapped_column(Integer, nullable=False)
    die_size_x: Mapped[int] = mapped_column(Integer, nullable=False)
    die_size_y: Mapped[int] = mapped_column(Integer, nullable=False)
    device: Mapped[str] = mapped_column(String(50), nullable=False)

    recipe: Mapped[InspRecipeORM | None] = relationship(
        "InspRecipeORM",
        primaryjoin=lambda: InspWaferSummaryORM.recipe_key
        == foreign(InspRecipeORM.recipe_key),
        viewonly=True,
        lazy="joined",
    )


class InspRecipeORM(Base):
    __tablename__ = "insp_recipe"

    recipe_key: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[str] = mapped_column(String(50), nullable=False)
    origin_index_x: Mapped[int] = mapped_column(Integer, nullable=False)
    origin_index_y: Mapped[int] = mapped_column(Integer, nullable=False)


class InspectImageORM(Base):
    __tablename__ = "inspect_image"

    wafer_key: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspection_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    defect_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_type: Mapped[str | None] = mapped_column(String, nullable=True)
    image_filespec: Mapped[str | None] = mapped_column(String, nullable=True)


class InspectDefectORM(Base):
    __tablename__ = "inspect_defect"

    wafer_key: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspection_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    defect_id: Mapped[int] = mapped_column(Integer, primary_key=True)
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
    die_x: Mapped[int] = mapped_column(Integer, nullable=False)
    die_y: Mapped[int] = mapped_column(Integer, nullable=False)
    size_x: Mapped[int] = mapped_column(Integer, nullable=False)
    size_y: Mapped[int] = mapped_column(Integer, nullable=False)
    size_d: Mapped[int] = mapped_column(Integer, nullable=False)
    area: Mapped[int] = mapped_column(Integer, nullable=False)
    final_bin: Mapped[int] = mapped_column(Integer, nullable=False)
    manual_bin: Mapped[int] = mapped_column(Integer, nullable=False)
    kill_ratio: Mapped[float] = mapped_column(nullable=False)


class ClassORM(Base):
    __tablename__ = "class"

    class_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)


class InspectionPatchImagesZipORM(BaseZips):
    __tablename__ = "inspection_patch_images_zip"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inspection_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    lot_id: Mapped[str] = mapped_column(String(50), nullable=False)
    wafer_id: Mapped[str] = mapped_column(String(50), nullable=False)
    device: Mapped[str] = mapped_column(String(50), nullable=False)
    layer_id: Mapped[str] = mapped_column(String(50), nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
