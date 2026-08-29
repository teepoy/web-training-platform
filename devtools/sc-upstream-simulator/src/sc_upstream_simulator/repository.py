from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Literal, cast

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .domain import (
    DefectDraft,
    InspectionDraft,
    InspectionKey,
    InspectionRecord,
    PatchArchiveDraft,
    Publication,
    ReviewImageDraft,
    _require_aware,
)
from .models import (
    DefectORM,
    InspectionORM,
    PatchArchiveORM,
    ReviewImageORM,
    SimulatorClockORM,
)


class SimulatorConflictError(RuntimeError):
    pass


class SimulatorRecordNotFoundError(LookupError):
    pass


class SimulatorStateError(RuntimeError):
    pass


class SimulatorNotInitializedError(RuntimeError):
    pass


@dataclass(frozen=True)
class InspectionChildCounts:
    defects: int
    review_images: int
    patch_archives: int


class SimulatorRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create_draft(self, draft: InspectionDraft) -> InspectionKey:
        key = draft.key
        try:
            async with self._sessions() as session, session.begin():
                inspection = InspectionORM(
                    wafer_key=key.wafer_key,
                    inspection_time=key.inspection_time,
                    lot_id=draft.lot_id,
                    wafer_id=draft.wafer_id,
                    layer_id=draft.layer_id,
                    device=draft.device,
                    inspect_equip_id=draft.inspect_equip_id,
                    recipe_key=draft.recipe_key,
                    recipe_id=draft.recipe_id,
                    origin_index_x=draft.origin_index_x,
                    origin_index_y=draft.origin_index_y,
                    center_x=draft.center_x,
                    center_y=draft.center_y,
                    origin_x=draft.origin_x,
                    origin_y=draft.origin_y,
                    die_size_x=draft.die_size_x,
                    die_size_y=draft.die_size_y,
                    state="draft",
                    published_at=None,
                    last_updated_at=None,
                    change_token=None,
                )
                session.add(inspection)
                await session.flush()
                session.add_all(
                    DefectORM(
                        wafer_key=key.wafer_key,
                        inspection_time=key.inspection_time,
                        **vars(defect),
                    )
                    for defect in draft.defects
                )
                session.add_all(
                    ReviewImageORM(
                        wafer_key=key.wafer_key,
                        inspection_time=key.inspection_time,
                        **vars(image),
                    )
                    for image in draft.review_images
                )
                session.add_all(
                    PatchArchiveORM(
                        wafer_key=key.wafer_key,
                        inspection_time=key.inspection_time,
                        **vars(archive),
                    )
                    for archive in draft.patch_archives
                )
        except IntegrityError as exc:
            raise SimulatorConflictError(
                "inspection or one of its child records already exists"
            ) from exc
        return key

    async def append_records(
        self,
        key: InspectionKey,
        *,
        defects: tuple[DefectDraft, ...],
        review_images: tuple[ReviewImageDraft, ...],
        patch_archives: tuple[PatchArchiveDraft, ...],
    ) -> None:
        if not defects and not review_images and not patch_archives:
            raise ValueError("at least one child record is required")
        try:
            async with self._sessions() as session, session.begin():
                inspection = await self._locked_inspection(session, key)
                if inspection.state != "draft":
                    raise SimulatorStateError(
                        "child records can only be appended to a draft inspection"
                    )
                session.add_all(
                    DefectORM(
                        wafer_key=key.wafer_key,
                        inspection_time=key.inspection_time,
                        **vars(defect),
                    )
                    for defect in defects
                )
                session.add_all(
                    ReviewImageORM(
                        wafer_key=key.wafer_key,
                        inspection_time=key.inspection_time,
                        **vars(image),
                    )
                    for image in review_images
                )
                session.add_all(
                    PatchArchiveORM(
                        wafer_key=key.wafer_key,
                        inspection_time=key.inspection_time,
                        **vars(archive),
                    )
                    for archive in patch_archives
                )
        except IntegrityError as exc:
            raise SimulatorConflictError(
                "one of the child records already exists"
            ) from exc

    async def publish(
        self, key: InspectionKey, *, published_at: datetime
    ) -> Publication:
        _require_aware(published_at, "published_at")
        if published_at < key.inspection_time:
            raise ValueError("published_at must not precede inspection_time")
        async with self._sessions() as session, session.begin():
            inspection = await self._locked_inspection(session, key)
            if inspection.state != "draft":
                raise SimulatorStateError("only a draft inspection can be published")

            change_token = await self._next_change_token(session)
            inspection.state = "published"
            inspection.published_at = published_at
            inspection.last_updated_at = published_at
            inspection.change_token = change_token

        return Publication(
            key=key,
            published_at=published_at,
            last_updated_at=published_at,
            change_token=change_token,
        )

    async def update_published(
        self,
        key: InspectionKey,
        *,
        changed_at: datetime,
        changes: Mapping[str, str | int],
    ) -> Publication:
        _require_aware(changed_at, "changed_at")
        if not changes:
            raise ValueError("at least one mutable field is required")
        allowed = {
            "lot_id",
            "wafer_id",
            "layer_id",
            "device",
            "inspect_equip_id",
            "recipe_key",
            "recipe_id",
            "origin_index_x",
            "origin_index_y",
            "center_x",
            "center_y",
            "origin_x",
            "origin_y",
            "die_size_x",
            "die_size_y",
        }
        unknown = set(changes).difference(allowed)
        if unknown:
            raise ValueError(
                f"unsupported mutable fields: {', '.join(sorted(unknown))}"
            )

        async with self._sessions() as session, session.begin():
            inspection = await self._locked_inspection(session, key)
            if inspection.state != "published":
                raise SimulatorStateError(
                    "only a published inspection can receive source updates"
                )
            if inspection.last_updated_at is None:
                raise SimulatorStateError(
                    "published inspection is missing last_updated_at"
                )
            current_last_updated_at = inspection.last_updated_at
            if current_last_updated_at.tzinfo is None:
                # SQLite drops timezone metadata in isolated unit tests. Runtime
                # settings reject SQLite, so production always receives a
                # timezone-aware PostgreSQL value.
                current_last_updated_at = current_last_updated_at.replace(
                    tzinfo=timezone.utc
                )
            if changed_at <= current_last_updated_at:
                raise SimulatorConflictError(
                    "changed_at must be later than the current last_updated_at"
                )

            for field_name, value in changes.items():
                setattr(inspection, field_name, value)
            change_token = await self._next_change_token(session)
            inspection.last_updated_at = changed_at
            inspection.change_token = change_token
            if inspection.published_at is None:
                raise SimulatorStateError(
                    "published inspection is missing published_at"
                )
            published_at = inspection.published_at

        return Publication(
            key=key,
            published_at=published_at,
            last_updated_at=changed_at,
            change_token=change_token,
        )

    async def get_inspection(self, key: InspectionKey) -> InspectionRecord:
        async with self._sessions() as session:
            inspection = await session.scalar(
                select(InspectionORM).where(
                    InspectionORM.wafer_key == key.wafer_key,
                    InspectionORM.inspection_time == key.inspection_time,
                )
            )
            if inspection is None:
                raise SimulatorRecordNotFoundError("inspection does not exist")
            return self._to_record(inspection)

    async def list_inspections(
        self, *, state: Literal["draft", "published"] | None
    ) -> tuple[InspectionRecord, ...]:
        query = select(InspectionORM)
        if state is not None:
            query = query.where(InspectionORM.state == state)
        query = query.order_by(
            InspectionORM.inspection_time.desc(), InspectionORM.wafer_key.desc()
        )
        async with self._sessions() as session:
            rows = (await session.scalars(query)).all()
            return tuple(self._to_record(row) for row in rows)

    async def check_ready(self) -> None:
        async with self._sessions() as session:
            clock = await session.get(SimulatorClockORM, 1)
            if clock is None:
                raise SimulatorNotInitializedError(
                    "simulator clock is missing; apply the database migrations"
                )

    async def child_counts(self, key: InspectionKey) -> InspectionChildCounts:
        async with self._sessions() as session:
            await self._require_inspection(session, key)
            predicates = (
                DefectORM.wafer_key == key.wafer_key,
                DefectORM.inspection_time == key.inspection_time,
            )
            defects = await session.scalar(
                select(func.count()).select_from(DefectORM).where(*predicates)
            )
            review_images = await session.scalar(
                select(func.count())
                .select_from(ReviewImageORM)
                .where(
                    ReviewImageORM.wafer_key == key.wafer_key,
                    ReviewImageORM.inspection_time == key.inspection_time,
                )
            )
            patch_archives = await session.scalar(
                select(func.count())
                .select_from(PatchArchiveORM)
                .where(
                    PatchArchiveORM.wafer_key == key.wafer_key,
                    PatchArchiveORM.inspection_time == key.inspection_time,
                )
            )
            return InspectionChildCounts(
                defects=int(defects or 0),
                review_images=int(review_images or 0),
                patch_archives=int(patch_archives or 0),
            )

    async def _next_change_token(self, session: AsyncSession) -> int:
        clock = await session.scalar(
            select(SimulatorClockORM).where(SimulatorClockORM.id == 1).with_for_update()
        )
        if clock is None:
            raise SimulatorNotInitializedError(
                "simulator clock is missing; apply the database migrations"
            )
        change_token = clock.next_change_token
        clock.next_change_token += 1
        return change_token

    @staticmethod
    def _to_record(inspection: InspectionORM) -> InspectionRecord:
        inspection_time = inspection.inspection_time
        if inspection_time.tzinfo is None:
            inspection_time = inspection_time.replace(tzinfo=timezone.utc)
        published_at = inspection.published_at
        if published_at is not None and published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        last_updated_at = inspection.last_updated_at
        if last_updated_at is not None and last_updated_at.tzinfo is None:
            last_updated_at = last_updated_at.replace(tzinfo=timezone.utc)
        return InspectionRecord(
            key=InspectionKey(
                wafer_key=inspection.wafer_key,
                inspection_time=inspection_time,
            ),
            lot_id=inspection.lot_id,
            wafer_id=inspection.wafer_id,
            layer_id=inspection.layer_id,
            device=inspection.device,
            inspect_equip_id=inspection.inspect_equip_id,
            recipe_key=inspection.recipe_key,
            recipe_id=inspection.recipe_id,
            origin_index_x=inspection.origin_index_x,
            origin_index_y=inspection.origin_index_y,
            center_x=inspection.center_x,
            center_y=inspection.center_y,
            origin_x=inspection.origin_x,
            origin_y=inspection.origin_y,
            die_size_x=inspection.die_size_x,
            die_size_y=inspection.die_size_y,
            state=cast(Literal["draft", "published"], inspection.state),
            published_at=published_at,
            last_updated_at=last_updated_at,
            change_token=inspection.change_token,
        )

    async def _locked_inspection(
        self, session: AsyncSession, key: InspectionKey
    ) -> InspectionORM:
        inspection = await session.scalar(
            select(InspectionORM)
            .where(
                InspectionORM.wafer_key == key.wafer_key,
                InspectionORM.inspection_time == key.inspection_time,
            )
            .with_for_update()
        )
        if inspection is None:
            raise SimulatorRecordNotFoundError("inspection does not exist")
        return inspection

    async def _require_inspection(
        self, session: AsyncSession, key: InspectionKey
    ) -> InspectionORM:
        inspection = await session.scalar(
            select(InspectionORM).where(
                InspectionORM.wafer_key == key.wafer_key,
                InspectionORM.inspection_time == key.inspection_time,
            )
        )
        if inspection is None:
            raise SimulatorRecordNotFoundError("inspection does not exist")
        return inspection
