"""Sparse-native prediction runner — outline (Phase 1 stub).

This module is intentionally a stub.  No implementation is shipped in Phase 1.

Flow sketch
-----------
1. Resolve the dataset manifest from storage (:class:`~app.modules.datasets.domain.entities.dataset_payload.DatasetManifest`).
2. Iterate over shard entries in order of ``shard_index``.
3. For each shard:
   a. Load the parquet shard bytes from object storage via ``ArtifactStorage``.
   b. Read rows in configurable batch sizes using :class:`~app.modules.datasets.application.services.sparse_manifest.SparseManifestReader`.
   c. For each row, map the parquet columns to the prediction runtime input
      (image_bytes, metadata, question/text).
   d. Call the model predictor via ``predictor.predict_single(ctx, input)``
      or the inference worker batch path.
   e. Collect results in-memory as :class:`~app.modules.datasets.domain.entities.dataset_payload.SparsePredictionResult`
      instances (not as DB-backed ``PlatformPrediction`` rows).
4. After all shards have been processed, serialize a
   :class:`~app.modules.datasets.domain.entities.dataset_payload.SparsePredictionJobResult` and
   its per-shard :class:`~app.modules.datasets.domain.entities.dataset_payload.SparsePredictionShard`
   children to object storage.

Integration point (in :meth:`PredictionService.run_prediction`)::

    if dataset.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE:
        runner = SparsePredictionRunner(
            repository=self.repository,
            artifact_storage=self.artifact_storage,
            config=self.config,
            embedding_client=self._embedding_client,
            llm_client=self._llm_client,
            inference_worker=self._inference_worker,
        )
        return await runner.run(model, dataset, model_version=version_tag,
                                target=target, prompt=prompt)


Storage contract
----------------
Prediction results for ``file_shard_sparse`` datasets are *not* persisted
as ``PlatformPrediction`` rows in the API database.  Instead they live as
parquet files in object storage, organised under the dataset prefix.

Write layout
~~~~~~~~~~~~
One prediction shard is written for every input dataset shard (1:1 mapping).
The naming convention is::

    datasets/{org_id}/{dataset_id}/predictions/{job_id}/{shard_index:06d}.parquet

Each shard file is a parquet table whose schema mirrors the fields of
:class:`~app.modules.datasets.domain.entities.dataset_payload.SparsePredictionResult`:

    shard_index, row_index, dataset_id,
    predicted_label, confidence, all_scores, error

A top-level job result manifest — serialized from
:class:`~app.modules.datasets.domain.entities.dataset_payload.SparsePredictionJobResult` — is
stored alongside the shards::

    datasets/{org_id}/{dataset_id}/predictions/{job_id}/job_result.json

This manifest lists every prediction shard URI so that readers never
need to scan object storage.

Read-back for review
~~~~~~~~~~~~~~~~~~~~
When the review/reclassify UI (T14) needs prediction results:

1. Load the ``job_result.json`` manifest to discover all prediction shard URIs.
2. For each :class:`~app.modules.datasets.domain.entities.dataset_payload.SparsePredictionShard`:
   a. Read the prediction parquet shard from object storage.
   b. Read the *original* dataset shard from
      ``datasets/{org_id}/{dataset_id}/shards/{shard_index:06d}.parquet``.
   c. Join the two on ``(shard_index, row_index)``, producing combined
      rows with both original sample data (image_uri, metadata, ...)
      and prediction fields (predicted_label, confidence, error).
3. Present the joined rows to the review UI, keyed by
   :class:`~app.modules.datasets.domain.entities.dataset_payload.SampleLocator`.

The :class:`~app.modules.datasets.domain.entities.dataset_payload.SparsePredictionJobResult`
domain model is the single source of truth for discovering and
paginating prediction results without a database round-trip.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omegaconf import DictConfig

    from app.shared.api.schemas import Dataset, Model
    from app.shared.db.sql_repository import SqlRepository
    from app.shared.infrastructure.workers.embedding import EmbeddingClient
    from app.shared.infrastructure.workers.inference_worker import InferenceWorkerClient
    from app.shared.infrastructure.llm.client import OpenAICompatibleLlmClient
    from app.shared.infrastructure.storage.base import ArtifactStorage


class SparsePredictionRunner:
    """Stub — dispatches sparse-native prediction across shards.

    Will read the dataset manifest, iterate shard rows in batches,
    run the model predictor (or inference worker) on every row, and
    store per-shard ``SparsePredictionResult`` parquet files in
    object storage.

    See the module-level docstring for the full storage contract.
    """

    def __init__(
        self,
        *,
        repository: SqlRepository,
        artifact_storage: ArtifactStorage,
        config: DictConfig,
        embedding_client: EmbeddingClient | None = None,
        llm_client: OpenAICompatibleLlmClient | None = None,
        inference_worker: InferenceWorkerClient | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_storage = artifact_storage
        self._config = config
        self._embedding_client = embedding_client
        self._llm_client = llm_client
        self._inference_worker = inference_worker

    async def run(
        self,
        model: Model,
        dataset: Dataset,
        *,
        org_id: str = "",
        model_version: str | None = None,
        target: str = "image_classification",
        prompt: str | None = None,
    ) -> None:
        """Entry point — not implemented in Phase 1.

        When implemented, writes one prediction shard per input shard
        to ``datasets/{org_id}/{dataset_id}/predictions/{job_id}/``
        and stores the ``job_result.json`` manifest.
        """
        raise NotImplementedError(
            "sparse_prediction.SparsePredictionRunner.run is a Phase 2 hook"
        )
