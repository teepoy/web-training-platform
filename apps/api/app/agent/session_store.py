"""In-memory conversation session store for the global agent.

Persists multi-turn conversation history keyed by ``session_id``.
Sessions have a configurable TTL; stale sessions are lazily evicted
on access.

Thread-safe via ``asyncio.Lock``.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Session:
    """A single agent conversation session."""

    session_id: str
    user_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)
    last_active: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_active = time.monotonic()


class SessionStore:
    """In-memory store for agent conversation sessions.

    Parameters
    ----------
    ttl_seconds:
        Sessions older than this (measured from ``last_active``) are
        evicted on the next access.  Default: 2 hours.
    max_sessions:
        Hard cap on total sessions.  When exceeded, the oldest session
        is evicted regardless of TTL.  Default: 500.
    max_messages_per_session:
        Maximum conversation messages to keep per session.  Older
        messages are truncated from the front (FIFO).  Default: 100.
    """

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evict_stale(self) -> None:
        """Remove sessions that have exceeded the TTL."""
        cutoff = time.monotonic() - self._ttl
        stale_keys = [k for k, s in self._sessions.items() if s.last_active < cutoff]
        for k in stale_keys:
            del self._sessions[k]

    def _enforce_cap(self) -> None:
        """If we're over the max, drop the oldest session."""
        while len(self._sessions) > self._max_sessions:
            oldest_key = min(self._sessions, key=lambda k: self._sessions[k].last_active)
            del self._sessions[oldest_key]

    def _truncate_messages(self, session: Session) -> None:
        """Keep only the last N messages."""
        if len(session.messages) > self._max_messages:
            session.messages = session.messages[-self._max_messages :]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_or_create(self, session_id: str, user_id: str) -> Session:
        """Return an existing session or create a new one."""
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
        """Return a session if it exists and is not stale."""
        async with self._lock:
            self._evict_stale()
            session = self._sessions.get(session_id)
            if session is not None:
                session.touch()
            return session

    async def append_messages(
        self, session_id: str, messages: list[dict[str, Any]]
    ) -> None:
        """Append messages to a session and truncate if needed."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            session.messages.extend(messages)
            self._truncate_messages(session)
            session.touch()

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Return a copy of the session message history."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return []
            return list(session.messages)

    async def clear_session(self, session_id: str) -> None:
        """Remove a session entirely."""
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def session_count(self) -> int:
        """Return the number of active sessions."""
        async with self._lock:
            self._evict_stale()
            return len(self._sessions)
