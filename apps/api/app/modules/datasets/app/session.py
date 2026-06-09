from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.core.mapper_registry import mapper
from app.core.registry import get_dataset_model
from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.datasets.domain.repository import DatasetRepository
from app.modules.datasets.domain.sample_row import SampleRow
from app.modules.datasets.domain.storage_agg import DatasetStorageAgg


def _resolve_projector(model_cls: type, dataset_type: str, view_type: str) -> Any:
    try:
        return mapper.get_mapper(dataset_type, view_type)
    except KeyError:
        pass
    try:
        return mapper.get_mapper(model_cls, view_type)
    except KeyError:
        pass
    raise KeyError(
        f"No mapper registered for ({dataset_type!r} | {model_cls!r}) -> {view_type!r}"
    )


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
        model_cls: type,
        dataset_type: str,
        access: DatasetStorageAgg,
        dataset_id: str,
    ) -> None:
        self._model_cls = model_cls
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
            order_by=order_by,
            sample_ids=sample_ids,
        )
        projector = _resolve_row_projector(view_type)
        view_rows: list[Any] = []
        for row in rows:
            if view_type == "patch_image_v1":
                view_rows.append(projector(row, dataset_id=self._dataset_id))
            else:
                view_rows.append(projector(row))
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
        if self._view_type == "patch_image_v1":
            return projector(row, dataset_id=dataset_id)
        return projector(row)


class DatasetSessionFactory:
    def __init__(
        self,
        repo: DatasetRepository,
        storage_factory: DatasetStorageFactory,
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

        model_cls = get_dataset_model(dataset.dataset_type)
        if model_cls is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"No model registered for dataset_type '{dataset.dataset_type}'"
                ),
            )

        try:
            _resolve_projector(model_cls, dataset.dataset_type, view_type)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        storage = await self._storage_factory.open(dataset_id, org_id)

        return DatasetSession(
            model_cls,
            dataset.dataset_type,
            storage,
            dataset_id,
        )
