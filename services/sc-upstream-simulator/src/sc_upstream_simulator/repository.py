from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .domain import InspectionDraft, InspectionKey, Publication, _require_aware
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

    async def publish(
        self, key: InspectionKey, *, published_at: datetime
    ) -> Publication:
        _require_aware(published_at, "published_at")
        async with self._sessions() as session, session.begin():
            inspection = await self._locked_inspection(session, key)
            if inspection.state != "draft":
                raise SimulatorStateError("only a draft inspection can be published")

            clock = await session.scalar(
                select(SimulatorClockORM)
                .where(SimulatorClockORM.id == 1)
                .with_for_update()
            )
            if clock is None:
                raise SimulatorNotInitializedError(
                    "simulator clock is missing; apply the database migrations"
                )

            change_token = clock.next_change_token
            clock.next_change_token += 1
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
