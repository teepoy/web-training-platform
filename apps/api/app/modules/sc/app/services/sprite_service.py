from __future__ import annotations

from typing import Any

from app.modules.sc.domain.image_fetcher import ScImageFetcher

PATCH_IMAGE_TYPES = ("PATCH_TEMPLATE", "PATCH_DEFECTIVE", "difference")
PATCH_CELL_SIZE = 64
REVIEW_CELL_SIZE = 224

pyvips = None  # type: ignore[assignment]


def _get_pyvips() -> Any:
    """Lazy-import pyvips to avoid GLib symbol conflicts at import time.

    Importing pyvips at module level triggers GLib/libvips symbol conflicts
    with torch and other native libraries loaded by the GPU training worker,
    causing SIGSEGV (exit code -11).
    """
    try:
        import pyvips  # pyright: ignore[reportMissingImports]
    except ImportError:
        raise ImportError(
            "pyvips is required for sprite generation but is not installed. "
            "Install it with: pip install pyvips"
        )
    return pyvips


class SpriteService:
    def __init__(self, image_fetcher: ScImageFetcher) -> None:
        self._image_fetcher = image_fetcher

    def _bytes_to_vips(self, data: bytes) -> Any:
        vips = _get_pyvips()
        return vips.Image.new_from_buffer(data, "")  # pyright: ignore[reportUnknownMemberType, reportReturnType]

    def _resize_cell(self, img: Any, size: int) -> Any:
        return img.thumbnail_image(size, height=size)  # type: ignore[return-value]

    async def _fetch_cell(
        self,
        inspection_time: str,
        wafer_key: int,
        defect_id: str,
        image_type: str,
        cell_size: int,
        review_image_id: int | None = None,
    ) -> Any:
        data = await self._image_fetcher.get_image_bytes(
            inspection_time=inspection_time,
            wafer_key=wafer_key,
            defect_id=defect_id,
            image_type=image_type,
            review_image_id=review_image_id,
        )
        img = self._bytes_to_vips(data)
        return self._resize_cell(img, cell_size)

    async def build_patch_sprite(
        self,
        inspection_time: str,
        wafer_key: int,
        defect_id: str,
        cell_size: int = PATCH_CELL_SIZE,
    ) -> bytes:
        vips = _get_pyvips()
        cells: list[Any] = []
        for img_type in PATCH_IMAGE_TYPES:
            cell = await self._fetch_cell(
                inspection_time=inspection_time,
                wafer_key=wafer_key,
                defect_id=defect_id,
                image_type=img_type,
                cell_size=cell_size,
            )
            cells.append(cell)

        sprite = vips.Image.arrayjoin(cells, across=len(cells))  # pyright: ignore[reportAttributeAccessIssue]
        return sprite.write_to_buffer(".png")

    async def build_review_sprite(
        self,
        inspection_time: str,
        wafer_key: int,
        defect_id: str,
        review_count: int = 3,
        cell_size: int = REVIEW_CELL_SIZE,
    ) -> bytes:
        vips = _get_pyvips()
        cells: list[Any] = []
        for img_type in PATCH_IMAGE_TYPES:
            cell = await self._fetch_cell(
                inspection_time=inspection_time,
                wafer_key=wafer_key,
                defect_id=defect_id,
                image_type=img_type,
                cell_size=cell_size,
            )
            cells.append(cell)

        for i in range(1, review_count + 1):
            cell = await self._fetch_cell(
                inspection_time=inspection_time,
                wafer_key=wafer_key,
                defect_id=defect_id,
                image_type="review",
                cell_size=cell_size,
                review_image_id=i,
            )
            cells.append(cell)

        sprite = vips.Image.arrayjoin(cells, across=len(cells))  # pyright: ignore[reportAttributeAccessIssue]
        return sprite.write_to_buffer(".png")

    async def build_patch_batch_sprite(
        self,
        inspection_time: str,
        wafer_key: int,
        defect_ids: list[str],
        cell_size: int = PATCH_CELL_SIZE,
    ) -> bytes:
        vips = _get_pyvips()
        patch_cols = len(PATCH_IMAGE_TYPES)
        cells: list[Any] = []
        for did in defect_ids:
            for img_type in PATCH_IMAGE_TYPES:
                cell = await self._fetch_cell(
                    inspection_time=inspection_time,
                    wafer_key=wafer_key,
                    defect_id=did,
                    image_type=img_type,
                    cell_size=cell_size,
                )
                cells.append(cell)

        sprite = vips.Image.arrayjoin(cells, across=patch_cols)  # pyright: ignore[reportAttributeAccessIssue]
        return sprite.write_to_buffer(".png")

    async def build_review_batch_sprite(
        self,
        inspection_time: str,
        wafer_key: int,
        defect_ids: list[str],
        review_count: int = 3,
        cell_size: int = REVIEW_CELL_SIZE,
    ) -> bytes:
        vips = _get_pyvips()
        review_cols = len(PATCH_IMAGE_TYPES) + review_count
        cells: list[Any] = []
        for did in defect_ids:
            for img_type in PATCH_IMAGE_TYPES:
                cell = await self._fetch_cell(
                    inspection_time=inspection_time,
                    wafer_key=wafer_key,
                    defect_id=did,
                    image_type=img_type,
                    cell_size=cell_size,
                )
                cells.append(cell)
            for i in range(1, review_count + 1):
                cell = await self._fetch_cell(
                    inspection_time=inspection_time,
                    wafer_key=wafer_key,
                    defect_id=did,
                    image_type="review",
                    cell_size=cell_size,
                    review_image_id=i,
                )
                cells.append(cell)

        sprite = vips.Image.arrayjoin(cells, across=review_cols)  # pyright: ignore[reportAttributeAccessIssue]
        return sprite.write_to_buffer(".png")
