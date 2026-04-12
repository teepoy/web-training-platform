"""In-memory surface state store.

Holds per-session panel state for agent-controlled display surfaces.
Thread-safe via asyncio.Lock.  State is JSON-serialisable and
supports export / import for persistence or sharing.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.api.schemas import AgentPanelDescriptor, SurfaceLayout, SurfaceStateDocument


class SurfaceStore:
    """In-memory store for display-surface panel state.

    Keyed by ``(session_id, surface_id)`` tuples.  All mutations are
    guarded by an ``asyncio.Lock`` so concurrent SSE-push handlers don't
    race.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # {session_id: {surface_id: SurfaceStateDocument}}
        self._state: dict[str, dict[str, SurfaceStateDocument]] = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure(self, session_id: str, surface_id: str) -> SurfaceStateDocument:
        """Return the state doc, creating a blank one if absent."""
        if session_id not in self._state:
            self._state[session_id] = {}
        if surface_id not in self._state[session_id]:
            self._state[session_id][surface_id] = SurfaceStateDocument(
                surface_id=surface_id,
            )
        return self._state[session_id][surface_id]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_state(
        self, session_id: str, surface_id: str
    ) -> SurfaceStateDocument:
        async with self._lock:
            return deepcopy(self._ensure(session_id, surface_id))

    async def get_panel(
        self, session_id: str, surface_id: str, panel_id: str
    ) -> AgentPanelDescriptor | None:
        async with self._lock:
            doc = self._ensure(session_id, surface_id)
            for p in doc.panels:
                if p.id == panel_id:
                    return deepcopy(p)
            return None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def set_panel(
        self, session_id: str, surface_id: str, panel: AgentPanelDescriptor
    ) -> SurfaceStateDocument:
        """Add or replace a panel.  Returns the updated document."""
        async with self._lock:
            doc = self._ensure(session_id, surface_id)
            # Replace existing or append
            replaced = False
            new_panels = []
            for existing in doc.panels:
                if existing.id == panel.id:
                    new_panels.append(deepcopy(panel))
                    replaced = True
                else:
                    new_panels.append(existing)
            if not replaced:
                new_panels.append(deepcopy(panel))
            doc.panels = sorted(new_panels, key=lambda p: p.order)
            return deepcopy(doc)

    async def remove_panel(
        self, session_id: str, surface_id: str, panel_id: str
    ) -> SurfaceStateDocument | None:
        """Remove a panel by id.  Returns updated doc, or None if not found."""
        async with self._lock:
            doc = self._ensure(session_id, surface_id)
            before = len(doc.panels)
            doc.panels = [p for p in doc.panels if p.id != panel_id]
            if len(doc.panels) == before:
                return None
            return deepcopy(doc)

    async def clear_ephemeral(
        self, session_id: str, surface_id: str
    ) -> SurfaceStateDocument:
        """Remove all panels marked ``ephemeral=True``."""
        async with self._lock:
            doc = self._ensure(session_id, surface_id)
            doc.panels = [p for p in doc.panels if not p.ephemeral]
            return deepcopy(doc)

    # ------------------------------------------------------------------
    # Bulk / Import-Export
    # ------------------------------------------------------------------

    async def import_state(
        self, session_id: str, surface_id: str, doc: SurfaceStateDocument
    ) -> SurfaceStateDocument:
        """Replace the entire surface state with a provided document."""
        async with self._lock:
            if session_id not in self._state:
                self._state[session_id] = {}
            imported = deepcopy(doc)
            imported.surface_id = surface_id
            self._state[session_id][surface_id] = imported
            return deepcopy(imported)

    async def export_state(
        self, session_id: str, surface_id: str
    ) -> SurfaceStateDocument:
        """Export the surface state with an ``exported_at`` timestamp."""
        async with self._lock:
            doc = deepcopy(self._ensure(session_id, surface_id))
            doc.exported_at = datetime.now(timezone.utc).isoformat()
            return doc

    # ------------------------------------------------------------------
    # Session cleanup
    # ------------------------------------------------------------------

    async def clear_session(self, session_id: str) -> None:
        async with self._lock:
            self._state.pop(session_id, None)

    async def clear_surface(self, session_id: str, surface_id: str) -> None:
        async with self._lock:
            if session_id in self._state:
                self._state[session_id].pop(surface_id, None)
