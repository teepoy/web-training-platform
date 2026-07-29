from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Any

from app.modules.storage.domain.data_plane import DataPlaneManifest

DEFAULT_PATCH_IMAGE_TYPES = ["patch_template", "patch_defective"]


@dataclass
class ScInspectionMaterialization:
    parquet_path: str
    dataset: Any
    row_count: int
    manifest: DataPlaneManifest
    errors: list[dict[str, str]] = field(default_factory=list)
    cache_dir: str | None = None

    def cleanup(self) -> None:
        if os.path.isfile(self.parquet_path):
            os.unlink(self.parquet_path)
        if self.cache_dir and os.path.isdir(self.cache_dir):
            shutil.rmtree(self.cache_dir, ignore_errors=True)
