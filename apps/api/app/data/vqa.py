from __future__ import annotations

from app.presets.runtime import DatasetRef


class VqaDatasetAdapter:
    """Dataset adapter for VQA records (image + question + optional answer)."""

    def __init__(self) -> None:
        self._records: list[dict] = []
        self._cursor = 0

    async def load(self, dataset_ref: DatasetRef) -> list[dict]:
        records = dataset_ref.metadata.get("records", [])
        if not isinstance(records, list):
            raise ValueError("dataset records must be a list")
        normalized: list[dict] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "sample_id": str(item.get("sample_id", "")),
                    "image_uri": str(item.get("image_uri", "")),
                    "question": str(item.get("question", "")),
                    "answer": str(item.get("answer", "")) if item.get("answer") is not None else None,
                }
            )
        self._records = normalized
        self._cursor = 0
        return self._records

    async def iterate_batches(self, batch_size: int):
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        while self._cursor < len(self._records):
            batch = self._records[self._cursor : self._cursor + batch_size]
            self._cursor += batch_size
            yield batch
