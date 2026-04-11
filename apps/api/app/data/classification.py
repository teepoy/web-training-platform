from __future__ import annotations

from app.presets.runtime import DatasetRef


class ImageClassificationAdapter:
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
            image_uri = str(item.get("image_uri", ""))
            label = str(item.get("label", ""))
            sample_id = str(item.get("sample_id", ""))
            if not image_uri:
                continue
            normalized.append(
                {
                    "sample_id": sample_id,
                    "image_uri": image_uri,
                    "label": label,
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


def build_train_loader(*args, **kwargs):
    return None


def build_infer_loader(*args, **kwargs):
    return None


def build_eval_loader(*args, **kwargs):
    return None
