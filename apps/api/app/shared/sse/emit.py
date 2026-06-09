from __future__ import annotations

from app.shared.sse.events import SSEEvent


def emit_sse(event: SSEEvent) -> str:
    return f"event: {event.root.event_type}\ndata: {event.model_dump_json()}\n\n"
