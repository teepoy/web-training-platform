from __future__ import annotations

from app.shared.api.schemas import Dataset


SC_PATCH_ARCHIVE_SOURCE_CONTRACT = "sc.patch_archive.v1"


def require_sc_patch_archive_profile(dataset: Dataset) -> str:
    binding = dataset.image_source
    if binding is None:
        raise ValueError(
            f"Dataset '{dataset.id}' has no image source binding; bind contract "
            f"'{SC_PATCH_ARCHIVE_SOURCE_CONTRACT}' and a deployment profile before "
            "running SC training or prediction"
        )
    if binding.contract != SC_PATCH_ARCHIVE_SOURCE_CONTRACT:
        raise ValueError(
            f"Dataset '{dataset.id}' image source contract {binding.contract!r} is "
            f"not compatible with {SC_PATCH_ARCHIVE_SOURCE_CONTRACT!r}"
        )
    profile = binding.profile.strip()
    if not profile:
        raise ValueError(f"Dataset '{dataset.id}' image source profile is empty")
    return profile


__all__ = ["SC_PATCH_ARCHIVE_SOURCE_CONTRACT", "require_sc_patch_archive_profile"]
