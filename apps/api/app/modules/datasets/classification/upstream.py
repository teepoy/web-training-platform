from __future__ import annotations

from collections.abc import AsyncIterator

from app.modules.datasets.classification.models import ClassificationSample


class ClassificationUpstreamAdapter:
    sample_model: type = ClassificationSample

    async def stream(
        self, source_uri: str, filters: dict | None = None
    ) -> AsyncIterator[ClassificationSample]:
        _ = source_uri
        _ = filters
        # Stub: yields mock samples for prototyping
        for i in range(5):
            yield ClassificationSample(
                sample_id=f"upstream-cls-{i}",
                image_uris=[f"https://example.com/img/{i}.jpg"],
                label="mock",
            )
