from __future__ import annotations

from collections.abc import AsyncIterator

from app.modules.datasets.detection.models import BoxV1, DetectionSample


class DetectionUpstreamAdapter:
    sample_model: type = DetectionSample

    async def stream(
        self, source_uri: str, filters: dict | None = None
    ) -> AsyncIterator[DetectionSample]:
        _ = source_uri
        _ = filters
        for i in range(3):
            yield DetectionSample(
                sample_id=f"upstream-det-{i}",
                image_uris=[f"https://example.com/det/{i}.jpg"],
                boxes=[BoxV1(label="object", x=10.0, y=10.0, width=50.0, height=50.0)],
            )
