from __future__ import annotations

from fastapi import HTTPException

from app.domain.models import Dataset
from app.domain.types import DatasetStorageMode


def assert_not_sparse(dataset: Dataset) -> None:
    """Raise 409 if *dataset* uses sparse storage mode.

    Many operations (sample creation, annotation sync, exports, etc.)
    require fully materialised samples and are incompatible with
    ``file_shard_sparse`` datasets.
    """
    if dataset.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
        raise HTTPException(
            status_code=409,
            detail="This operation is not supported for file_shard_sparse datasets",
        )
