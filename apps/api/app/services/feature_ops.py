from __future__ import annotations

import base64
import math

from app.domain.models import Sample


class FeatureOpsService:
    def __init__(self, repository=None, embedding_service=None, inference_worker=None):
        self._repo = repository
        self._embedding_service = embedding_service
        self._inference_worker = inference_worker

    async def extract_features(self, samples: list[Sample], embed_model: str, force: bool = False, storage=None) -> dict:
        computed = 0
        skipped = 0
        for sample in samples:
            existing = await self._repo.get_sample_feature(sample.id)
            if existing is not None and existing.embed_model == embed_model and not force:
                skipped += 1
                continue
            if not sample.image_uris:
                skipped += 1
                continue
            uri = sample.image_uris[0]
            try:
                if uri.startswith("data:"):
                    _, encoded = uri.split(",", 1)
                    image_bytes = base64.b64decode(encoded)
                elif storage is not None:
                    image_bytes = await storage.get_bytes(uri)
                else:
                    skipped += 1
                    continue
                embedding = await self._embedding_service.embed_image(image_bytes, model_name=embed_model)
                await self._repo.upsert_sample_feature(sample.id, embedding, embed_model)
                computed += 1
            except Exception:
                skipped += 1
        return {
            "count": len(samples),
            "computed": computed,
            "skipped": skipped,
            "embedding_model": embed_model,
            "status": "completed",
        }

    async def extract_features_via_worker(self, samples: list[Sample], embed_model: str, force: bool = False, storage=None) -> dict:
        computed = 0
        skipped = 0
        payload_samples: list[dict] = []
        selected_samples: list[Sample] = []
        for sample in samples:
            existing = await self._repo.get_sample_feature(sample.id)
            if existing is not None and existing.embed_model == embed_model and not force:
                skipped += 1
                continue
            if not sample.image_uris:
                skipped += 1
                continue
            uri = sample.image_uris[0]
            try:
                if uri.startswith("data:"):
                    _, encoded = uri.split(",", 1)
                    image_bytes = base64.b64decode(encoded)
                elif storage is not None:
                    image_bytes = await storage.get_bytes(uri)
                else:
                    skipped += 1
                    continue
            except Exception:
                skipped += 1
                continue
            payload_samples.append({"sample_id": sample.id, "image_bytes": image_bytes})
            selected_samples.append(sample)
        if not payload_samples:
            return {
                "count": len(samples),
                "computed": computed,
                "skipped": skipped,
                "embedding_model": embed_model,
                "status": "completed",
            }
        if self._inference_worker is None:
            raise ValueError("Inference worker is not configured")
        embeddings = await self._inference_worker.embed_batch(model_name=embed_model, samples=payload_samples)
        embedding_map = {str(item.get("sample_id", "")): item for item in embeddings}
        for sample in selected_samples:
            item = embedding_map.get(sample.id)
            if item is None or item.get("error"):
                skipped += 1
                continue
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                skipped += 1
                continue
            await self._repo.upsert_sample_feature(sample.id, [float(v) for v in embedding], embed_model)
            computed += 1
        return {
            "count": len(samples),
            "computed": computed,
            "skipped": skipped,
            "embedding_model": embed_model,
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

    async def uniqueness_scores(self, sample_ids: list[str], dataset_id: str) -> dict:
        scores: dict[str, float] = {}
        for sid in sample_ids:
            feature = await self._repo.get_sample_feature(sid)
            if feature is None or not feature.embedding:
                continue
            neighbors = await self._repo.similarity_search(feature.embedding, dataset_id=dataset_id, k=5, exclude_id=sid)
            best = max((float(n.get("score", 0.0)) for n in neighbors), default=0.0)
            scores[sid] = round(1.0 - max(0.0, min(1.0, best)), 4)
        return scores

    async def representativeness_scores(self, sample_ids: list[str], dataset_id: str) -> dict:
        scores: dict[str, float] = {}
        for sid in sample_ids:
            feature = await self._repo.get_sample_feature(sid)
            if feature is None or not feature.embedding:
                continue
            neighbors = await self._repo.similarity_search(feature.embedding, dataset_id=dataset_id, k=10, exclude_id=sid)
            if not neighbors:
                scores[sid] = 0.0
                continue
            avg = sum(float(n.get("score", 0.0)) for n in neighbors) / len(neighbors)
            scores[sid] = round(max(0.0, min(1.0, avg)), 4)
        return scores

    async def uncovered_cluster_hints(self, dataset_id: str) -> dict:
        samples, _ = await self._repo.list_samples(dataset_id, limit=100_000)
        if not samples:
            return {"dataset_id": dataset_id, "clusters": []}
        annotations = await self._repo.list_annotations_for_dataset(dataset_id)
        labels_by_sample: dict[str, str] = {}
        for ann in sorted(annotations, key=lambda a: a.created_at):
            labels_by_sample[ann.sample_id] = ann.label

        clusters: dict[str, dict[str, int]] = {}
        sizes: dict[str, int] = {}
        for sample in samples:
            feat = await self._repo.get_sample_feature(sample.id)
            if feat is None or not feat.embedding:
                continue
            vec = feat.embedding
            if not vec:
                continue
            key = f"c{int(abs(vec[0]) * 10)}"
            clusters.setdefault(key, {})
            sizes[key] = sizes.get(key, 0) + 1
            label = labels_by_sample.get(sample.id)
            if label:
                clusters[key][label] = clusters[key].get(label, 0) + 1

        out = []
        for cid, label_counts in clusters.items():
            size = sizes.get(cid, 0)
            dominant = ""
            dominant_ratio = 0.0
            if label_counts:
                dominant, count = max(label_counts.items(), key=lambda x: x[1])
                dominant_ratio = count / max(1, size)
            if size < 3:
                continue
            if not label_counts:
                hint = "cluster has embeddings but no annotations yet"
            elif dominant_ratio < 0.6:
                hint = "cluster mixes labels; boundary review recommended"
            else:
                hint = f"cluster mostly '{dominant}'"
            out.append({"cluster_id": cid, "size": size, "hint": hint})
        out.sort(key=lambda x: x["size"], reverse=True)
        return {"dataset_id": dataset_id, "clusters": out[:5]}
