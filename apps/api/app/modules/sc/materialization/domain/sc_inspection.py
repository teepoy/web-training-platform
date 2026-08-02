from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.modules.storage.domain.data_plane import DataPlaneManifest

DEFAULT_PATCH_IMAGE_TYPES = ["patch_template", "patch_defective"]


@dataclass
class ScInspectionMaterialization:
    parquet_path: str
    row_count: int
    manifest: DataPlaneManifest
    errors: list[dict[str, str]] = field(default_factory=list)

    def cleanup(self) -> None:
        if os.path.isfile(self.parquet_path):
            os.unlink(self.parquet_path)
