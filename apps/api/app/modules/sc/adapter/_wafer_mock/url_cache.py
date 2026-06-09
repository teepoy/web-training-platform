from __future__ import annotations

import time
from collections.abc import Callable


class PresignedUrlCache:
    """In-memory cache for presigned S3 URLs to avoid regenerating per-request."""

    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[str, float]] = {}

    def get_or_generate(self, key: str, generator: Callable[[], str]) -> str:
        now = time.time()
        if key in self._cache:
            url, expiry = self._cache[key]
            if now < expiry:
                return url

        url = generator()
        self._cache[key] = (url, now + self._ttl_seconds)
        return url

    def clear(self) -> None:
        self._cache.clear()
