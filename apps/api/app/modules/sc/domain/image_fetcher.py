from __future__ import annotations

from typing import Protocol


class ScImageFetcher(Protocol):
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

    async def get_image_bytes_batch(
        self,
        *,
        inspection_time: str,
        wafer_key: int,
        images: list[dict[str, object]],
    ) -> list[dict[str, object]]: ...

    async def warm_cache(
        self,
        *,
        inspection_time: str,
        wafer_key: int,
        defect_ids: list[int] | None = None,
    ) -> dict[str, object]: ...

    async def close(self) -> None: ...
