from __future__ import annotations

from collections.abc import AsyncIterator

from app.modules.datasets.vqa.models import VQASample


class VQAUpstreamAdapter:
    sample_model: type = VQASample

    async def stream(
        self, source_uri: str, filters: dict | None = None
    ) -> AsyncIterator[VQASample]:
        _ = source_uri
        _ = filters
        for i in range(3):
            yield VQASample(
                sample_id=f"upstream-vqa-{i}",
                image_uris=[f"https://example.com/vqa/{i}.jpg"],
                question="What is in this image?",
                answer="mock answer",
            )
