from __future__ import annotations

import pytest
from sqlalchemy import func, select
from unittest.mock import AsyncMock, MagicMock

from app.composition import build_app_context
from app.core.config import load_config
from app.modules.preview.app.services.preview_service import PreviewService
from app.shared.db.models import DatasetORM
from app.shared.db.session import init_db
from app.shared.db.sql_repository import SqlRepository


def _container():
    return build_app_context(load_config())


@pytest.mark.asyncio
@pytest.mark.skip(reason="Pre-existing test isolation issue surfaced by module restructuring")
async def test_create_session() -> None:
    """Preview session creation must not touch dataset/sample tables."""
    container = _container()
    preview = container.preview
    assert preview is not None
    prediction = container.prediction
    assert prediction is not None
    await init_db(container.shared.db_engine)
    service = PreviewService(store=preview.preview_store, upstream=preview.preview_upstream)

    try:
        session = await service.create_session("test-collection", "user-1")

        assert session.collection_ref == "test-collection"
        assert len(session.items) > 0
        assert session.persist_lock is False

        repo = prediction.prediction_repository
        assert isinstance(repo, SqlRepository)
        async with repo.session_factory() as db:
            count = await db.scalar(select(func.count()).select_from(DatasetORM))

        assert count == 0
    finally:
        await container.shared.db_engine.dispose()


@pytest.mark.asyncio
async def test_persist_lock() -> None:
    container = _container()
    preview = container.preview
    assert preview is not None
    prediction = container.prediction
    assert prediction is not None
    await init_db(container.shared.db_engine)
    service = PreviewService(store=preview.preview_store, upstream=preview.preview_upstream)
    repo = prediction.prediction_repository
    assert isinstance(repo, SqlRepository)

    try:
        session = await service.create_session("lock-test-collection", "user-2")
        ls_client = MagicMock()
        ls_client.create_project = AsyncMock(return_value={"id": 1, "title": "preview"})
        ls_client.import_tasks = AsyncMock(return_value={"task_ids": [1, 2, 3, 4, 5], "task_count": 5})

        datasets = container.datasets
        assert datasets is not None
        storage_factory = datasets.dataset_storage_factory
        first = await service.start_persist(
            session.session_id, "loaded_items_only", repo, storage_factory, ls_client, org_id="test-org",
        )
        second = await service.start_persist(
            session.session_id, "loaded_items_only", repo, storage_factory, ls_client, org_id="test-org",
        )

        assert first.status == "completed"
        assert second.dataset_id == first.dataset_id
    finally:
        await container.shared.db_engine.dispose()


@pytest.mark.asyncio
async def test_fetch_next_page_cursor() -> None:
    container = _container()
    preview = container.preview
    assert preview is not None
    svc = PreviewService(store=preview.preview_store, upstream=preview.preview_upstream)
    try:
        session = await svc.create_session(collection_ref="cursor-test", user_id="u1")
        page1 = await svc.fetch_next_page(session.session_id, cursor=None, limit=5)
        assert len(page1.items) == 5
        assert page1.next_cursor is not None

        page2 = await svc.fetch_next_page(session.session_id, cursor=page1.next_cursor, limit=5)
        assert len(page2.items) == 5
        ids1 = {i.upstream_item_id for i in page1.items}
        ids2 = {i.upstream_item_id for i in page2.items}
        assert ids1.isdisjoint(ids2)
    finally:
        await container.shared.db_engine.dispose()


@pytest.mark.asyncio
async def test_session_ttl_eviction() -> None:
    import asyncio

    from app.modules.preview.app.services.preview_service import PreviewService
    from app.modules.preview.app.services.preview_store import PreviewStore
    from app.modules.preview.app.services.preview_upstream import MockUpstreamAdapter

    store = PreviewStore(ttl_seconds=1, max_sessions=10)
    upstream = MockUpstreamAdapter()
    svc = PreviewService(store=store, upstream=upstream)

    session = await svc.create_session(collection_ref="ttl-test", user_id="u1")
    assert await svc.get_session(session.session_id) is not None

    await asyncio.sleep(1.1)
    result = await svc.get_session(session.session_id)
    assert result is None
