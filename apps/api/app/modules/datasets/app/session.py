from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.core.mapper_registry import mapper
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.modules.datasets.domain.compatibility import (
    DatasetCompatibilityError,
    validate_view_for_dataset,
)
from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.datasets.domain.sample_row import SampleRow
from app.modules.datasets.domain.view_projection import ViewProjectionContext
from app.modules.storage.domain.storage_agg import DatasetStorageAgg


def _resolve_row_projector(view_type: str) -> Any:
    """Resolve a direct ``SampleRow -> view_type`` mapper.

    All view types have ``SampleRow -> view`` mappers registered in
    ``datasets/domain/mapper.py``.  This returns the mapper callable
    directly without going through the two-step ``Sample -> domain -> view``
    chain that breaks when fed ``SampleRow`` objects.
    """
    return mapper.get_mapper(SampleRow, view_type)


class DatasetSession:
    def __init__(
        self,
        dataset_type: str,
        access: DatasetStorageAgg,
        dataset_id: str,
    ) -> None:
        self._dataset_type = dataset_type
        self._access = access
        self._dataset_id = dataset_id

    async def list_samples(
        self,
        view_type: str,
        offset: int = 0,
        limit: int = 50,
        order_by: str = "id",
        sample_ids: list[str] | None = None,
    ) -> tuple[list[Any], int]:
        rows, total = await self._access.list_samples(
            offset=offset,
            limit=limit,
            with_labels=True,
            with_predictions=True,
            order_by=order_by,
            sample_ids=sample_ids,
        )
        projector = _resolve_row_projector(view_type)
        context = ViewProjectionContext(
            dataset_id=self._dataset_id,
            dataset_type=self._dataset_type,
        )
        view_rows: list[Any] = []
        for row in rows:
            view_rows.append(projector(row, context=context))
        return view_rows, total


class SessionViewLoader:
    def __init__(
        self,
        session: DatasetSession,
        view_type: str,
        *,
        annotated_only: bool,
        length: int,
    ) -> None:
        self._session = session
        self._view_type = view_type
        self._annotated_only = annotated_only
        self._len = length
        self._indices: list[int] | None = None

    @classmethod
    async def create(
        cls,
        session: DatasetSession,
        view_type: str,
        *,
        annotated_only: bool = False,
    ) -> SessionViewLoader:
        storage: DatasetStorageAgg = session._access

        if annotated_only:
            _, total = await storage.list_samples(
                offset=0, limit=1, label_filter="__annotated__"
            )
            length = total
        else:
            _, total = await storage.list_samples(offset=0, limit=1)
            length = total

        instance = cls(session, view_type, annotated_only=annotated_only, length=length)
        return instance

    def __len__(self) -> int:
        return self._len

    @property
    def annotated_only(self) -> bool:
        return self._annotated_only

    async def get_item(self, index: int) -> Any:
        if index < 0 or index >= self._len:
            raise IndexError(
                f"Index {index} out of range for "
                f"dataset {self._session._dataset_id} "
                f"(len={self._len}, annotated_only={self._annotated_only})"
            )

        dataset_id = self._session._dataset_id
        storage: DatasetStorageAgg = self._session._access

        if self._annotated_only:
            rows, _ = await storage.list_samples(
                offset=index, limit=1, label_filter="__annotated__"
            )
        else:
            rows, _ = await storage.list_samples(offset=index, limit=1)

        row = rows[0] if rows else None
        if row is None:
            raise ValueError(
                f"Sample at logical index {index} "
                f"could not be resolved for dataset {dataset_id}"
            )

        projector = _resolve_row_projector(self._view_type)
        context = ViewProjectionContext(
            dataset_id=dataset_id,
            dataset_type=self._session._dataset_type,
        )
        return projector(row, context=context)


class DatasetSessionFactory:
    def __init__(
        self,
        repo: DatasetRepository,
        storage_factory: DatasetStorageFactoryPort,
    ) -> None:
        self._repo = repo
        self._storage_factory = storage_factory

    async def create(
        self,
        dataset_id: str,
        view_type: str,
        org_id: str,
    ) -> DatasetSession:
        dataset = await self._repo.get_dataset(dataset_id, org_id=org_id)
        if dataset is None:
            raise HTTPException(status_code=404, detail="Dataset not found")

        try:
            validate_view_for_dataset(view_type, dataset.view_types)
            _resolve_row_projector(view_type)
        except (DatasetCompatibilityError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        storage = await self._storage_factory.open(dataset_id, org_id)

        return DatasetSession(
            dataset.dataset_type,
            storage,
            dataset_id,
        )
