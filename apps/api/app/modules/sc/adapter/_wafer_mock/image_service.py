from __future__ import annotations

import base64
from urllib.parse import quote, urlencode

from app.modules.sc.wafer_data_gen import (
    NUM_CLASSES,
    patch_image_for_class,
    review_image_for_class,
)

from .cache import PatchCacheProtocol, PatchImageCache


class ScImageService:
    def __init__(
        self,
        cache: PatchCacheProtocol | None = None,
        api_prefix: str = "/api/v1",
    ) -> None:
        self._cache = cache or PatchImageCache()
        self._api_prefix = api_prefix.rstrip("/")

    def proxy_url(
        self,
        *,
        inspection_time: str,
        wafer_key: int,
        defect_id: str,
        image_type: str,
        s3_path: str | None = None,
    ) -> str:
        path = "/".join(
            [
                self._api_prefix,
                "sc",
                "images",
                quote(inspection_time, safe=""),
                str(wafer_key),
                quote(defect_id, safe=""),
                quote(image_type, safe=""),
            ]
        )
        if s3_path is None:
            return path
        return f"{path}?{urlencode({'s3_path': s3_path})}"

    async def get_image_bytes(
        self,
        *,
        inspection_time: str,
        wafer_key: int,
        defect_id: str,
        image_type: str,
        s3_path: str | None = None,
        review_image_id: int | None = None,
    ) -> bytes:
        try:
            defect_idx = int(defect_id)
        except ValueError:
            return b""
        class_idx = (defect_idx - 1) % NUM_CLASSES

        if image_type in ("review",):
            uri = review_image_for_class(class_idx)
        else:
            uri = patch_image_for_class(class_idx)

        if uri.startswith("data:"):
            _, encoded = uri.split(",", 1)
            return base64.b64decode(encoded)
        return b""
