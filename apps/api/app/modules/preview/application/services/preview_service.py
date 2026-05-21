from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from app.shared.api.schemas import Dataset, Sample, TaskSpec
from app.modules.preview.domain.entities.preview import (
    PreviewPage,
    PreviewPersistScope,
    PreviewPersistStatus,
    PreviewSession,
)
from app.shared.api.schemas import DatasetType, TaskType
from app.modules.preview.application.services.preview_store import PreviewStore
from app.modules.preview.application.services.preview_upstream import UpstreamAdapter

if TYPE_CHECKING:
    from app.shared.db.sql_repository import SqlRepository
    from app.shared.domain.protocols import LabelStudioClient


class PreviewService:
    def __init__(self, store: PreviewStore, upstream: UpstreamAdapter) -> None:
        self._store = store
        self._upstream = upstream

    async def create_session(self, collection_ref: str, user_id: str) -> PreviewSession:
        await self._upstream.resolve_collection(collection_ref)
        first_page = await self._upstream.fetch_page(collection_ref, None, 20)
        session_id = str(uuid4())
        return await self._store.create(session_id, collection_ref, user_id, first_page)

    async def get_session(self, session_id: str) -> PreviewSession | None:
        return await self._store.get(session_id)

    async def fetch_next_page(
        self, session_id: str, cursor: str | None, limit: int
    ) -> PreviewPage:
        session = await self._store.get(session_id)
        if session is None:
            raise KeyError(f"Preview session {session_id!r} not found or expired")
        page = await self._upstream.fetch_page(session.collection_ref, cursor, limit)
        await self._store.append_page(session_id, page)
        return page

    async def start_persist(
        self,
        session_id: str,
        scope: PreviewPersistScope,
        dataset_repo: SqlRepository,
        label_studio_client: LabelStudioClient,
    ) -> PreviewPersistStatus:
        session = await self._store.get(session_id)
        if session is None:
            raise KeyError(f"Preview session {session_id!r} not found or expired")

        if not session.can_start_persist():
            if session.persist_status is not None:
                return session.persist_status
            return PreviewPersistStatus(
                dataset_id="",
                persist_session_id=session_id,
                status="pending",
                imported_count=0,
                remaining_count=0,
                error=None,
            )

        session.start_persist()

        from app.modules.datasets.domain import schemas as _schemas  # noqa: F401 — triggers schema registration
        from app.shared.infrastructure.label_studio.client import (
            LabelStudioClient as _LSC,
        )

        upstream_schema = self._upstream.get_dataset_schema()

        if upstream_schema is not None:
            dataset_type = DatasetType(upstream_schema.dataset_type)
            task_type = TaskType(upstream_schema.task_type)
            label_space: list[str] = []
            label_config = upstream_schema.generate_ls_config(label_space)
        else:
            dataset_type = DatasetType.IMAGE_CLASSIFICATION
            task_type = TaskType.CLASSIFICATION
            label_config = _LSC.generate_image_classification_config([])

        project = await label_studio_client.create_project(
            f"Preview: {session.collection_ref}", label_config
        )
        ls_project_id = str(project.get("id", ""))

        dataset = Dataset(
            name=f"Preview: {session.collection_ref}",
            dataset_type=dataset_type,
            task_spec=TaskSpec(task_type=task_type),
            ls_project_id=ls_project_id,
        )
        dataset = await dataset_repo.create_dataset(dataset)

        if scope == "entire_collection":
            page = await self._upstream.fetch_page(
                session.collection_ref, cursor=None, limit=2000
            )
            items = page.items
        else:
            items = session.items

        samples = [
            Sample(
                dataset_id=dataset.id,
                image_uris=item.image_uris,
                metadata=item.metadata,
            )
            for item in items
        ]

        if samples:
            await dataset_repo.create_samples(samples)

        status = PreviewPersistStatus(
            dataset_id=dataset.id,
            persist_session_id=str(uuid4()),
            status="completed",
            imported_count=len(samples),
            remaining_count=0,
            error=None,
        )
        await self._store.set_persist_status(session_id, status)
        return status

    async def get_persist_status(self, session_id: str) -> PreviewPersistStatus | None:
        session = await self._store.get(session_id)
        if session is None:
            return None
        return session.persist_status
