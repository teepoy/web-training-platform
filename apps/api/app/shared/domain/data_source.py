from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class RuntimeDataSourceRef:
    kind: Literal["dataset", "collection_revision"]
    dataset_id: str | None = None
    collection_id: str | None = None
    collection_revision_id: str | None = None

    @classmethod
    def from_fields(
        cls,
        *,
        dataset_id: str | None,
        collection_id: str | None,
        collection_revision_id: str | None,
    ) -> RuntimeDataSourceRef:
        normalized_dataset_id = _clean(dataset_id)
        normalized_collection_id = _clean(collection_id)
        normalized_revision_id = _clean(collection_revision_id)
        if normalized_dataset_id is not None:
            if (normalized_collection_id is None) != (normalized_revision_id is None):
                raise ValueError(
                    "collection_id and collection_revision_id must be provided together"
                )
            return cls(
                kind="dataset",
                dataset_id=normalized_dataset_id,
                collection_id=normalized_collection_id,
                collection_revision_id=normalized_revision_id,
            )
        if normalized_collection_id is None or normalized_revision_id is None:
            raise ValueError(
                "provide dataset_id or both collection_id and collection_revision_id"
            )
        return cls(
            kind="collection_revision",
            collection_id=normalized_collection_id,
            collection_revision_id=normalized_revision_id,
        )

    @property
    def identity(self) -> str:
        if self.kind == "dataset":
            assert self.dataset_id is not None
            return self.dataset_id
        assert self.collection_id is not None
        assert self.collection_revision_id is not None
        return f"{self.collection_id}@{self.collection_revision_id}"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


__all__ = ["RuntimeDataSourceRef"]
