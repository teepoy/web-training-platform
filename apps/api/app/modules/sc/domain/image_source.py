from __future__ import annotations

from app.shared.api.schemas import Dataset


FILESYSTEM_IMAGE_SOURCE_CONTRACT = "filesystem.image-source.v1"
SC_LEGACY_RANGE_ZIP_FORMAT = "sc.legacy-range-zip.v1"


def require_sc_image_source_format(dataset: Dataset) -> str:
    binding = dataset.image_source
    if binding is None:
        raise ValueError(
            f"Dataset '{dataset.id}' has no image source binding; bind contract "
            f"'{FILESYSTEM_IMAGE_SOURCE_CONTRACT}' and an explicit source format before "
            "running SC training or prediction"
        )
    source_format = (binding.format or "").strip()
    if not source_format:
        raise ValueError(
            f"Dataset '{dataset.id}' image source format is missing; historical "
            "profile bindings are not inferred or backfilled"
        )
    if binding.contract != FILESYSTEM_IMAGE_SOURCE_CONTRACT:
        raise ValueError(
            f"Dataset '{dataset.id}' image source contract {binding.contract!r} is "
            f"not compatible with {FILESYSTEM_IMAGE_SOURCE_CONTRACT!r}"
        )
    return source_format


__all__ = [
    "FILESYSTEM_IMAGE_SOURCE_CONTRACT",
    "SC_LEGACY_RANGE_ZIP_FORMAT",
    "require_sc_image_source_format",
]
