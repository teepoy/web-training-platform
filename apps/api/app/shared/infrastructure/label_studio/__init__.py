from __future__ import annotations

from typing import Any

from app.shared.infrastructure.label_studio.client import LabelStudioClient

_INSTANCE: LabelStudioClient | None = None


def init_label_studio(cfg: Any) -> None:
    global _INSTANCE

    _INSTANCE = LabelStudioClient(
        url=str(cfg.label_studio.url),
        api_key=str(cfg.label_studio.api_key),
    )


def get_label_studio() -> LabelStudioClient:
    if _INSTANCE is None:
        raise RuntimeError("Label Studio infrastructure has not been initialized")
    return _INSTANCE
