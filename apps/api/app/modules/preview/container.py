from __future__ import annotations

from dataclasses import dataclass

from app.modules.preview.app.services.preview_store import PreviewStore
from app.modules.preview.app.services.preview_upstream import (
    MockUpstreamAdapter,
    PreviewUpstreamRouter,
    UpstreamAdapter,
)
from app.shared.context import SharedInfra


@dataclass
class PreviewContext:
    preview_store: PreviewStore
    preview_upstream: UpstreamAdapter


def init_preview(shared: SharedInfra) -> PreviewContext:
    return PreviewContext(
        preview_store=PreviewStore(),
        preview_upstream=PreviewUpstreamRouter(
            upstreams={"mock": MockUpstreamAdapter()}
        ),
    )
