from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from app.shared.domain.data_plane import DataPlaneManifest


def parquet_paths_from_manifest(manifest: DataPlaneManifest) -> tuple[Path, ...]:
    if manifest.view_contract != "sc.patch_image.v1":
        raise ValueError(
            "SC runtimes require view contract 'sc.patch_image.v1', got "
            f"{manifest.view_contract!r}"
        )
    if manifest.view_schema_version != "1":
        raise ValueError(
            "SC runtimes require view schema version '1', got "
            f"{manifest.view_schema_version!r}"
        )
    if manifest.format != "parquet" or not manifest.shards:
        raise ValueError("SC runtimes require one or more Parquet shards")

    paths: list[Path] = []
    for shard in manifest.shards:
        if shard.format != "parquet":
            raise ValueError("SC runtimes require every shard to be Parquet")
        parsed = urlparse(shard.uri)
        if parsed.scheme != "file":
            raise ValueError("SC local runtimes require file:// Parquet shards")
        paths.append(Path(unquote(parsed.path)))
    return tuple(paths)


sc_parquet_paths_from_manifest = parquet_paths_from_manifest

__all__ = ["parquet_paths_from_manifest", "sc_parquet_paths_from_manifest"]
