from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.db.models import DatasetORM
from app.db.session import init_db
from app.main import container


@pytest.mark.asyncio
async def test_create_session() -> None:
    """Preview session creation must not touch dataset/sample tables."""
    await init_db(container.db_engine())
    service = container.preview_service()

    session = await service.create_session("test-collection", "user-1")

    assert session.collection_ref == "test-collection"
    assert len(session.items) > 0
    assert session.persist_lock is False

    repo = container.repository()
    async with repo.session_factory() as db:
        count = await db.scalar(select(func.count()).select_from(DatasetORM))

    assert count == 0


@pytest.mark.asyncio
async def test_persist_lock() -> None:
    await init_db(container.db_engine())
    service = container.preview_service()
    repo = container.repository()

    session = await service.create_session("lock-test-collection", "user-2")
    ls_client = container.label_studio_client()

    first = await service.start_persist(session.session_id, "loaded_items_only", repo, ls_client)
    second = await service.start_persist(session.session_id, "loaded_items_only", repo, ls_client)

    assert first.status == "completed"
    assert second.dataset_id == first.dataset_id


@pytest.mark.asyncio
async def test_fetch_next_page_cursor() -> None:
    from app.main import container

    svc = container.preview_service()
    session = await svc.create_session(collection_ref="cursor-test", user_id="u1")
    page1 = await svc.fetch_next_page(session.session_id, cursor=None, limit=5)
    assert len(page1.items) == 5
    assert page1.next_cursor is not None

    page2 = await svc.fetch_next_page(session.session_id, cursor=page1.next_cursor, limit=5)
    assert len(page2.items) == 5
    ids1 = {i.upstream_item_id for i in page1.items}
    ids2 = {i.upstream_item_id for i in page2.items}
    assert ids1.isdisjoint(ids2)


@pytest.mark.asyncio
async def test_session_ttl_eviction() -> None:
    import asyncio

    from app.services.preview_service import PreviewService
    from app.services.preview_store import PreviewStore
    from app.services.preview_upstream import MockUpstreamAdapter

    store = PreviewStore(ttl_seconds=1, max_sessions=10)
    upstream = MockUpstreamAdapter()
    svc = PreviewService(store=store, upstream=upstream)

    session = await svc.create_session(collection_ref="ttl-test", user_id="u1")
    assert await svc.get_session(session.session_id) is not None

    await asyncio.sleep(1.1)
    result = await svc.get_session(session.session_id)
    assert result is None
