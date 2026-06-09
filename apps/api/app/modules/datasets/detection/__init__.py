from __future__ import annotations

from app.modules.datasets.detection.models import (
    BoxDetectionV1,
    BoxV1,
    DetectionDataset,
    DetectionSample,
    ImageInputV1,
)
from app.modules.datasets.detection.upstream import DetectionUpstreamAdapter

__all__ = [
    "BoxDetectionV1",
    "BoxV1",
    "DetectionDataset",
    "DetectionSample",
    "DetectionUpstreamAdapter",
    "ImageInputV1",
]
