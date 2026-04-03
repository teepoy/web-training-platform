from __future__ import annotations

from app.domain.models import Sample


class FeatureOpsService:
    def __init__(self, repository=None, embedding_service=None):
        self._repo = repository
        self._embedding_service = embedding_service

    def extract_features(self, samples: list[Sample]) -> dict:
        return {
            "count": len(samples),
            "embedding_model": "mock-clip-vit-b32",
            "status": "completed",
        }

    async def similarity_search(self, sample_id: str, dataset_id: str, k: int = 5) -> dict:
        """Return k nearest neighbors by cosine similarity."""
        # Get the query embedding
        feature = await self._repo.get_sample_feature(sample_id)
        if feature is None or not feature.embedding:
            # No embedding yet — trigger on-demand embed
            # Get the sample's image and embed it
            sample = await self._repo.get_sample(sample_id)
            if sample is None or not sample.image_uris:
                return {"sample_id": sample_id, "neighbors": []}
            # For simplicity, return empty if no embedding exists yet
            # (The UI will show "embed first" message)
            return {"sample_id": sample_id, "neighbors": []}

        embedding = feature.embedding

        # Try pgvector first, fall back to SQLite cosine
        neighbors = await self._repo.similarity_search(embedding, dataset_id, k, exclude_id=sample_id)
        return {"sample_id": sample_id, "neighbors": neighbors}

    def uniqueness_scores(self, sample_ids: list[str]) -> dict:
        return {sid: round(0.5 + (idx * 0.03), 3) for idx, sid in enumerate(sample_ids)}

    def representativeness_scores(self, sample_ids: list[str]) -> dict:
        return {sid: round(0.9 - (idx * 0.02), 3) for idx, sid in enumerate(sample_ids)}

    def uncovered_cluster_hints(self, dataset_id: str) -> dict:
        return {
            "dataset_id": dataset_id,
            "clusters": [
                {"cluster_id": "c1", "size": 23, "hint": "potential unseen class in others"},
                {"cluster_id": "c2", "size": 11, "hint": "high overlap with class A/B boundary"},
            ],
        }
