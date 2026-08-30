from __future__ import annotations

import zipfile
from pathlib import Path


def validate_yolo_sc_model_artifact(path: Path, artifact_format: str) -> None:
    """Validate the import-safe container contract for a YOLO SC checkpoint."""
    if artifact_format != "pytorch":
        raise ValueError("YOLO SC model artifacts must use the pytorch format")
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("YOLO SC model artifact is empty")
    if not zipfile.is_zipfile(path):
        raise ValueError("YOLO SC model artifact is not a PyTorch ZIP checkpoint")
    try:
        with zipfile.ZipFile(path) as checkpoint:
            corrupt_member = checkpoint.testzip()
            if corrupt_member is not None:
                raise ValueError(
                    f"YOLO SC model artifact contains a corrupt member: {corrupt_member}"
                )
            names = checkpoint.namelist()
    except zipfile.BadZipFile as exc:
        raise ValueError(
            "YOLO SC model artifact is not a valid ZIP checkpoint"
        ) from exc
    if not any(name.endswith("/data.pkl") for name in names):
        raise ValueError(
            "YOLO SC model artifact is missing PyTorch checkpoint metadata"
        )
    if not any(name.endswith("/version") for name in names):
        raise ValueError("YOLO SC model artifact is missing its PyTorch format version")


__all__ = ["validate_yolo_sc_model_artifact"]
