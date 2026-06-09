from __future__ import annotations

from typing import Protocol


class ScImageFetcher(Protocol):
    """Protocol for fetching SC wafer inspection images.

    Implementations handle image lookup and caching without exposing
    raw-data storage details to the API module.
    """

    def proxy_url(
        self,
        *,
        inspection_time: str,
        wafer_key: int,
        defect_id: str,
        image_type: str,
        s3_path: str | None = None,
    ) -> str: ...

    async def get_image_bytes(
        self,
        *,
        inspection_time: str,
        wafer_key: int,
        defect_id: str,
        image_type: str,
        s3_path: str | None = None,
        review_image_id: int | None = None,
    ) -> bytes: ...
