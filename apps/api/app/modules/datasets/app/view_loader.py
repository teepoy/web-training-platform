"""Minimal view-loader contract for training/prediction.

Provides indexed, view-projected access to dataset rows without materializing
all records into memory.  Consumers (trainers, predictors, exporters)
implement against this Protocol instead of depending on
``TrainContext.training_data`` or making direct ``SampleAccess`` calls.

Implementations wrap:
* A storage-mode-aware :class:`SampleAccess` backend (``DbFullSampleAccess``
    or ``_SparseSampleAccess``)
* Mapper-registry lookups that resolve sample conversion and view projection
* A ``view_type`` string selecting the projection target

Example training flow usage::

    from app.modules.datasets.app.view_loader import DatasetViewLoader

    async def train(
        ctx: TrainContext, *, view: DatasetViewLoader[ImageInputV1Row]
    ) -> TrainResult:
        for i in range(len(view)):
            item = await view.get_item(i)
            # item: ImageInputV1Row (typed view row)

No ``training_data`` fallback — the view-loader contract is the sole
data path for training and prediction flows.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

T_co = TypeVar("T_co", covariant=True)
"""Covariant type variable for the view-projected item returned by
:meth:`DatasetViewLoader.get_item`.  Binds to the concrete view-row type
selected by the caller (e.g. ``ImageInputV1Row``, ``LabeledImageV1Row``,
``ScPatchImageV1Row``).
"""


class DatasetViewLoader(Protocol[T_co]):
    """Minimal contract for indexed, view-projected dataset access.

    Exposes a flat integer-indexed sequence where each position resolves
    to a typed view row produced by the dataset model's view adapter.

     The implementation is responsible for:
     1. Resolving ``dataset_id`` + ``view_type`` → model class + mapper
     2. Using the correct ``SampleAccess`` backend for the dataset's
         ``storage_mode`` (``db_full`` or ``file_shard_sparse``)
     3. Projecting each raw row through the registered sample mapper and
         view-projection mapper

    Consumers only call ``__len__`` and ``get_item`` — they never interact
    with ``SampleAccess``, ``DatasetSession``, or storage-mode details
    directly.
    """

    def __len__(self) -> int:
        """Total number of view-projected items available.

        When :attr:`annotated_only` is ``True`` the count reflects only
        samples that have at least one annotation.  Otherwise every sample
        in the dataset is included.

        Returns:
            Non-negative integer item count.
        """
        ...

    async def get_item(self, index: int) -> T_co:
        """Fetch a single view-projected item by zero-based position.

        The underlying implementation reads the raw row via
        :class:`SampleAccess`, converts it to the dataset model via the
        registered sample mapper, then projects it through the registered
        view-projection mapper for ``view_type``.

        Args:
            index: Zero-based position in the logical item sequence.
                Must satisfy ``0 <= index < len(self)``.

        Returns:
            A typed view row (e.g. ``ImageInputV1Row``, ``LabeledImageV1Row``,
            ``ScPatchImageV1Row``) produced by the view adapter.

        Raises:
            IndexError: If *index* is out of range.
            ValueError: If the underlying storage cannot resolve the item
                (missing row, corrupt shard, missing annotation when
                ``annotated_only`` is ``True``, etc.).
        """
        ...

    @property
    def annotated_only(self) -> bool:
        """Whether the loader filters to only annotated samples.

        When ``True``:

        * ``__len__()`` counts only samples that have at least one
          annotation.
        * ``get_item(i)`` maps logical index *i* to the *i*-th annotated
          sample in the dataset, skipping unannotated ones.

        When ``False`` (default):
          all samples regardless of annotation status are included.
        """
        ...
