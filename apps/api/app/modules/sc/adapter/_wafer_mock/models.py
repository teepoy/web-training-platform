from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, and_
from sqlalchemy.orm import DeclarativeBase, Mapped, foreign, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class InspWaferSummaryORM(Base):
    __tablename__ = "insp_wafer_summary"

    wafer_key: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspection_time: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    lot_id: Mapped[str] = mapped_column(String(50), nullable=False)
    wafer_id: Mapped[str] = mapped_column(String(50), nullable=False)
    layer_id: Mapped[str] = mapped_column(String(50), nullable=False)
    recipe_key: Mapped[int] = mapped_column(Integer, nullable=False)
    inspect_equip_id: Mapped[str] = mapped_column(String(50), nullable=False)
    last_update: Mapped[datetime] = mapped_column(DateTime, nullable=False)
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


class InspectDefectORM(Base):
    __tablename__ = "inspect_defect"

    wafer_key: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspection_time: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
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

    review_images: Mapped[list[InspectImageORM]] = relationship(
        "InspectImageORM",
        primaryjoin=lambda: and_(
            InspectDefectORM.wafer_key == foreign(InspectImageORM.wafer_key),
            InspectDefectORM.inspection_time
            == foreign(InspectImageORM.inspection_time),
            InspectDefectORM.defect_id == foreign(InspectImageORM.defect_id),
        ),
        order_by="InspectImageORM.image_id.asc()",
        viewonly=True,
        lazy="selectin",
    )


class InspectImageORM(Base):
    __tablename__ = "inspect_image"

    wafer_key: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspection_time: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    defect_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_type: Mapped[str | None] = mapped_column(String, nullable=True)
    image_filespec: Mapped[str | None] = mapped_column(String, nullable=True)


class ClassORM(Base):
    __tablename__ = "class"

    class_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
