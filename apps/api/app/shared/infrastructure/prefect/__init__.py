from __future__ import annotations

from typing import Any

from app.shared.infrastructure.prefect.client import PrefectClient

_INSTANCE: PrefectClient | None = None


def init_prefect(cfg: Any) -> None:
    global _INSTANCE

    _INSTANCE = PrefectClient(prefect_api_url=str(cfg.prefect.api_url))


def get_prefect() -> PrefectClient:
    if _INSTANCE is None:
        raise RuntimeError("Prefect infrastructure has not been initialized")
    return _INSTANCE
