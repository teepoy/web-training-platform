from __future__ import annotations

import asyncio


class EmbeddingService:
    _models: dict = {}      # class-level cache keyed by model_name
    _processors: dict = {}  # class-level cache keyed by model_name

    def __init__(self, model_name: str = "openai/clip-vit-base-patch32"):
        self.model_name = model_name

    def _load_model(self, model_name: str):
        """Lazy-load CLIP for a given model_name. Called only on first embed per model."""
        if model_name not in self.__class__._models:
            from transformers import CLIPProcessor, CLIPModel
            processor = CLIPProcessor.from_pretrained(model_name)
            model = CLIPModel.from_pretrained(model_name)
            model.eval()
            self.__class__._processors[model_name] = processor
            self.__class__._models[model_name] = model
        return self.__class__._models[model_name], self.__class__._processors[model_name]

    def _embed_sync(self, image_bytes: bytes, model_name: str) -> list[float]:
        """Sync. Must be called via asyncio.to_thread()."""
        import torch
        from PIL import Image
        import io
        model, processor = self._load_model(model_name)
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        inputs = processor(images=image, return_tensors="pt")
        with torch.no_grad():
            features = model.get_image_features(**inputs)
            # normalize
            features = features / features.norm(dim=-1, keepdim=True)
        return features[0].tolist()  # list of 512 floats

    async def embed_image(self, image_bytes: bytes, model_name: str = "openai/clip-vit-base-patch32") -> list[float]:
        return await asyncio.to_thread(self._embed_sync, image_bytes, model_name)

    async def embed_batch(self, image_bytes_list: list[bytes], model_name: str = "openai/clip-vit-base-patch32") -> list[list[float]]:
        results = []
        for b in image_bytes_list:
            results.append(await self.embed_image(b, model_name))
        return results
