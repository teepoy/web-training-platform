from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from litellm.types.llms.openai import AllMessageValues  # type: ignore[import-untyped]


@dataclass
class Session:
    """A single agent conversation session."""

    session_id: str
    user_id: str
    messages: list[AllMessageValues] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)
    last_active: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_active = time.monotonic()


class SessionStore:
    """Thread-safe in-memory store for agent conversation sessions."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 7200,
        max_sessions: int = 500,
        max_messages_per_session: int = 100,
    ) -> None:
        self._lock = asyncio.Lock()
        self._sessions: dict[str, Session] = {}
        self._ttl = ttl_seconds
        self._max_sessions = max_sessions
        self._max_messages = max_messages_per_session

    def _evict_stale(self) -> None:
        cutoff = time.monotonic() - self._ttl
        stale_keys = [
            key
            for key, session in self._sessions.items()
            if session.last_active < cutoff
        ]
        for key in stale_keys:
            del self._sessions[key]

    def _enforce_cap(self) -> None:
        while len(self._sessions) > self._max_sessions:
            oldest_key = min(
                self._sessions, key=lambda key: self._sessions[key].last_active
            )
            del self._sessions[oldest_key]

    def _truncate_messages(self, session: Session) -> None:
        if len(session.messages) > self._max_messages:
            session.messages = session.messages[-self._max_messages :]

    async def get_or_create(self, session_id: str, user_id: str) -> Session:
        async with self._lock:
            self._evict_stale()
            if session_id in self._sessions:
                session = self._sessions[session_id]
                session.touch()
                return session
            session = Session(session_id=session_id, user_id=user_id)
            self._sessions[session_id] = session
            self._enforce_cap()
            return session

    async def get(self, session_id: str) -> Session | None:
        async with self._lock:
            self._evict_stale()
            session = self._sessions.get(session_id)
            if session is not None:
                session.touch()
            return session

    async def append_messages(
        self, session_id: str, messages: list[AllMessageValues]
    ) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            session.messages.extend(messages)
            self._truncate_messages(session)
            session.touch()

    async def get_messages(self, session_id: str) -> list[AllMessageValues]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return []
            return list(session.messages)

    async def clear_session(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def session_count(self) -> int:
        async with self._lock:
            self._evict_stale()
            return len(self._sessions)


__all__ = ["Session", "SessionStore"]
