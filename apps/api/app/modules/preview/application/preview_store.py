from __future__ import annotations

import asyncio
import time

from app.modules.preview.domain.preview import (
    PreviewPage,
    PreviewPersistStatus,
    PreviewSession,
)


class PreviewStore:
    def __init__(
        self,
        *,
        ttl_seconds: int = 7200,
        max_sessions: int = 200,
        max_items_per_session: int = 2000,
    ) -> None:
        self._lock = asyncio.Lock()
        self._sessions: dict[str, PreviewSession] = {}
        self._seen_item_ids: dict[str, set[str]] = {}
        self._ttl = ttl_seconds
        self._max_sessions = max_sessions
        self._max_items = max_items_per_session

    def _evict_stale(self) -> None:
        cutoff = time.monotonic() - self._ttl
        stale_keys = [k for k, s in self._sessions.items() if s.last_active < cutoff]
        for k in stale_keys:
            del self._sessions[k]
            self._seen_item_ids.pop(k, None)

    def _drop_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._seen_item_ids.pop(session_id, None)

    def _enforce_cap(self) -> None:
        while len(self._sessions) > self._max_sessions:
            oldest_key = min(
                self._sessions, key=lambda k: self._sessions[k].last_active
            )
            self._drop_session(oldest_key)

    def _truncate_items(self, session: PreviewSession) -> None:
        if len(session.items) > self._max_items:
            session.items = session.items[-self._max_items :]

    def _append_unique_items(
        self, session_id: str, session: PreviewSession, items: list
    ) -> None:
        seen = self._seen_item_ids.setdefault(session_id, set())
        for item in items:
            if item.upstream_item_id in seen:
                continue
            seen.add(item.upstream_item_id)
            session.items.append(item)
        self._truncate_items(session)

    async def create(
        self,
        session_id: str,
        collection_ref: str,
        user_id: str,
        first_page: PreviewPage,
    ) -> PreviewSession:
        async with self._lock:
            self._evict_stale()
            session = PreviewSession(
                session_id=session_id,
                collection_ref=collection_ref,
                user_id=user_id,
                next_cursor=first_page.next_cursor,
                estimated_total=first_page.estimated_total,
            )
            self._sessions[session_id] = session
            self._seen_item_ids[session_id] = set()
            self._append_unique_items(session_id, session, first_page.items)
            self._enforce_cap()
            return session

    async def get(self, session_id: str) -> PreviewSession | None:
        async with self._lock:
            self._evict_stale()
            session = self._sessions.get(session_id)
            if session is not None:
                session.touch()
            return session

    async def append_page(self, session_id: str, page: PreviewPage) -> int:
        async with self._lock:
            self._evict_stale()
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            self._append_unique_items(session_id, session, page.items)
            session.next_cursor = page.next_cursor
            session.estimated_total = page.estimated_total
            session.touch()
            return len(session.items)

    async def start_persist(self, session_id: str) -> bool:
        async with self._lock:
            self._evict_stale()
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            session.touch()
            return session.start_persist()

    async def set_persist_status(
        self, session_id: str, status: PreviewPersistStatus
    ) -> None:
        async with self._lock:
            self._evict_stale()
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            session.persist_status = status
            session.touch()

    async def session_count(self) -> int:
        async with self._lock:
            self._evict_stale()
            return len(self._sessions)
