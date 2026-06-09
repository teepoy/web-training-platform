from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.shared.api.schemas import DatasetStorageMode


@dataclass
class Capabilities:
    """Feature flags a storage backend advertises."""

    can_write_samples: bool = True
    can_list_samples: bool = True
    can_random: bool = True
    can_similarity: bool = True
    can_materialize: bool = True
    can_lazyframe: bool = True


@dataclass
class MaterializeResult:
    """Result of a materialization operation."""

    manifest_uri: str
    runtime_bucket: str
    prefix: str = ""
    row_count: int = 0
    schema_version: str = ""


class DatasetStorageAgg(Protocol):
    """Aggregate protocol for all dataset storage operations.

    Implementations wrap a single dataset's storage backend and expose
    the full set of read/write/search/materialize operations.
    """

    @property
    def dataset_id(self) -> str: ...

    @property
    def storage_mode(self) -> DatasetStorageMode: ...

    @property
    def capabilities(self) -> Capabilities: ...

    async def get_dataset_metadata(self) -> Any: ...

    async def list_samples(
        self,
        offset: int = 0,
        limit: int = 50,
        *,
        with_labels: bool = False,
        with_predictions: bool = False,
        prediction_job_id: str | None = None,
        label_filter: str | None = None,
        order_by: str = "id",
        random_seed: int | None = None,
        sample_ids: list[str] | None = None,
        return_lazyframe: bool = False,
    ) -> tuple[list[Any], int] | Any: ...

    async def get_sample(self, sample_id: str) -> Any | None: ...

    async def get_samples_batch(self, sample_ids: list[str]) -> list[Any | None]: ...

    async def update_sample_image_uris(
        self, sample_id: str, image_uris: list[str]
    ) -> Any | None: ...

    async def write_samples(
        self,
        rows: Any,
        *,
        schema_columns: list[Any] | None = None,
        batch_size: int = 1000,
    ) -> int: ...

    async def create_annotations(self, annotations: list[Any]) -> int: ...

    async def update_annotations(self, updates: list[tuple[str, str]]) -> int: ...

    async def delete_annotations(self, annotation_ids: list[str]) -> int: ...

    async def get_annotation_stats(self) -> dict: ...

    async def list_annotations(
        self,
        *,
        sample_id: str | None = None,
        dataset_id: str | None = None,
        limit: int | None = None,
    ) -> list[Any]: ...

    async def write_predictions(
        self,
        results: Any,
        *,
        job_id: str,
        model_id: str,
        model_version: str | None = None,
        batch_size: int = 500,
    ) -> int: ...

    async def prediction_summary(self) -> dict: ...

    async def upsert_sample_feature(
        self,
        sample_id: str,
        embedding: list[float],
        embed_model: str,
    ) -> None: ...

    async def similarity_search(
        self,
        embedding: list[float],
        k: int,
        exclude_id: str = "",
    ) -> list[dict]: ...

    async def materialize(self) -> Any: ...

    async def as_hf_dataset(
        self,
        view_id: str,
        *,
        sampling: int | None = None,
        sample_ids: list[str] | None = None,
    ) -> Any: ...

    async def recent_annotations(self, limit: int = 20) -> dict: ...

    async def delete_samples(self, sample_ids: list[str]) -> int: ...

    async def delete(self) -> None: ...
