"""In-memory surface state store."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone

from app.shared.api.schemas import AgentPanelDescriptor, SurfaceStateDocument


class SurfaceStore:
    """Thread-safe per-session display-surface panel store."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._state: dict[str, dict[str, SurfaceStateDocument]] = {}

    def _ensure(self, session_id: str, surface_id: str) -> SurfaceStateDocument:
        if session_id not in self._state:
            self._state[session_id] = {}
        if surface_id not in self._state[session_id]:
            self._state[session_id][surface_id] = SurfaceStateDocument(
                surface_id=surface_id,
            )
        return self._state[session_id][surface_id]

    async def get_state(self, session_id: str, surface_id: str) -> SurfaceStateDocument:
        async with self._lock:
            return deepcopy(self._ensure(session_id, surface_id))

    async def get_panel(
        self, session_id: str, surface_id: str, panel_id: str
    ) -> AgentPanelDescriptor | None:
        async with self._lock:
            doc = self._ensure(session_id, surface_id)
            for panel in doc.panels:
                if panel.id == panel_id:
                    return deepcopy(panel)
            return None

    async def set_panel(
        self, session_id: str, surface_id: str, panel: AgentPanelDescriptor
    ) -> SurfaceStateDocument:
        async with self._lock:
            doc = self._ensure(session_id, surface_id)
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
            doc.panels = sorted(new_panels, key=lambda item: item.order)
            return deepcopy(doc)

    async def remove_panel(
        self, session_id: str, surface_id: str, panel_id: str
    ) -> SurfaceStateDocument | None:
        async with self._lock:
            doc = self._ensure(session_id, surface_id)
            before = len(doc.panels)
            doc.panels = [panel for panel in doc.panels if panel.id != panel_id]
            if len(doc.panels) == before:
                return None
            return deepcopy(doc)

    async def clear_ephemeral(
        self, session_id: str, surface_id: str
    ) -> SurfaceStateDocument:
        async with self._lock:
            doc = self._ensure(session_id, surface_id)
            doc.panels = [panel for panel in doc.panels if not panel.ephemeral]
            return deepcopy(doc)

    async def import_state(
        self, session_id: str, surface_id: str, doc: SurfaceStateDocument
    ) -> SurfaceStateDocument:
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
        async with self._lock:
            doc = deepcopy(self._ensure(session_id, surface_id))
            doc.exported_at = datetime.now(timezone.utc).isoformat()
            return doc

    async def clear_session(self, session_id: str) -> None:
        async with self._lock:
            self._state.pop(session_id, None)

    async def clear_surface(self, session_id: str, surface_id: str) -> None:
        async with self._lock:
            if session_id in self._state:
                self._state[session_id].pop(surface_id, None)
