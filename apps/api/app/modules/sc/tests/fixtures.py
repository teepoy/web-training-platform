from __future__ import annotations

"""SC-owned test fixtures for wafer mock data.

Re-exports the mock upstream adapter classes so SC tests import from a single
SC-owned location instead of from the external ``wafer_mock`` package.

Usage in SC tests::

    from app.modules.sc.tests.fixtures import PatchImageCache, SqliteScUpstream
"""

from app.modules.sc.adapter._wafer_mock.cache import (
    CacheError,
    CacheFetchError,
    CacheLockTimeout,
    PatchImageCache,
)
from app.modules.sc.adapter._wafer_mock.sqlite_upstream import SqliteScUpstream
from app.modules.sc.adapter._wafer_mock.url_cache import PresignedUrlCache

__all__ = [
    "CacheError",
    "CacheFetchError",
    "CacheLockTimeout",
    "PatchImageCache",
    "PresignedUrlCache",
    "SqliteScUpstream",
]
