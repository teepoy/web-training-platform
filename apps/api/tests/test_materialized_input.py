from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.modules.runtime.domain.context import PredictionRuntimeContext
from app.modules.runtime.domain.events import RuntimeExecutionError
from app.modules.sc.runtime.materialized_input import sc_parquet_paths_from_manifest
from app.shared.domain.data_plane import DataPlaneManifest, DataPlaneShard


def _manifest(path: str) -> DataPlaneManifest:
    schema = pa.schema(
        [
            pa.field("sample_id", pa.string()),
            pa.field("patch_template_bytes", pa.binary()),
            pa.field("patch_defective_bytes", pa.binary()),
        ]
    )
    return DataPlaneManifest.from_schema(
        view_contract="sc.patch_image.v1",
        view_schema_version="1",
        dataset_id="dataset-1",
        job_id="job-1",
        format="parquet",
        schema=schema,
        schema_ref="arrow-schema://sc.patch_image.v1/1",
        image_encoding="embedded_bytes",
        image_roles=("patch_template", "patch_defective"),
        shards=(
            DataPlaneShard(
                uri=f"file://{path}",
                format="parquet",
                row_count=1,
            ),
        ),
        row_count=1,
    )


def test_sc_manifest_resolves_local_parquet_paths_in_order(tmp_path) -> None:
    parquet_path = tmp_path / "materialized.parquet"
    pq.write_table(
        pa.table(
            {
                "sample_id": ["sample-1"],
                "patch_template_bytes": [b"template"],
                "patch_defective_bytes": [b"defective"],
            }
        ),
        parquet_path,
    )

    assert sc_parquet_paths_from_manifest(_manifest(str(parquet_path))) == (
        parquet_path,
    )


def test_sc_manifest_rejects_non_file_shards(tmp_path) -> None:
    manifest = _manifest(str(tmp_path / "materialized.parquet"))
    remote_manifest = DataPlaneManifest(
        **{
            **manifest.__dict__,
            "shards": (
                DataPlaneShard(
                    uri="s3://bucket/materialized.parquet",
                    format="parquet",
                    row_count=1,
                ),
            ),
        }
    )

    with pytest.raises(ValueError, match="file://"):
        sc_parquet_paths_from_manifest(remote_manifest)


@pytest.mark.asyncio
async def test_sc_prediction_workspace_streams_manifest_and_checkpoint_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.sc.runtime.prediction_workspace import (
        open_sc_prediction_workspace,
    )

    parquet_path = tmp_path / "materialized.parquet"
    manifest = _manifest(str(parquet_path))
    cleanup_called = False

    def cleanup() -> None:
        nonlocal cleanup_called
        cleanup_called = True

    materializer = SimpleNamespace()

    async def materialize(**kwargs):
        assert kwargs["rows_lazyframe"] == "rows"
        assert kwargs["dataset_id"] == "dataset-1"
        return SimpleNamespace(
            manifest=manifest,
            errors=[{"sample_id": "broken"}],
            cleanup=cleanup,
        )

    materializer.materialize = materialize

    class Injector:
        def get(self, _interface: object) -> object:
            return materializer

    class Storage:
        async def get_file(self, uri: str, destination: str) -> None:
            assert uri == "memory://model.pt"
            Path(destination).write_bytes(b"checkpoint")

    created_paths: list[tuple[Path, ...]] = []

    def prediction_dataset(paths):
        normalized = tuple(paths)
        created_paths.append(normalized)
        return SimpleNamespace(paths=normalized)

    monkeypatch.setitem(
        sys.modules,
        "ml_library.data_loading",
        SimpleNamespace(ScPredictionDataset=prediction_dataset),
    )
    app_context = cast(
        Any,
        SimpleNamespace(
            injector=Injector(),
            shared=SimpleNamespace(
                artifact_storage=Storage(),
                config=SimpleNamespace(
                    sc=SimpleNamespace(
                        pipeline=SimpleNamespace(
                            prediction_max_materialized_bytes=1024
                        )
                    )
                ),
            ),
        ),
    )
    runtime_ctx = PredictionRuntimeContext(
        app_context=app_context,
        job_id="job-1",
        dataset_id="dataset-1",
        model_id="model-1",
        org_id="org-1",
        predictor_id="resnet50-sc-v1",
        created_by="user-1",
        target="image_classification",
    )

    async with open_sc_prediction_workspace(
        runtime_ctx,
        rows="rows",
        source_identity="dataset-1",
        model_uri="memory://model.pt",
    ) as workspace:
        checkpoint_path = workspace.checkpoint_path
        assert checkpoint_path.read_bytes() == b"checkpoint"
        assert workspace.materialization_error_count == 1
        assert workspace.dataset is not None

    assert created_paths == [(parquet_path,)]
    assert cleanup_called is True
    assert not checkpoint_path.exists()


@pytest.mark.asyncio
async def test_sc_training_fails_after_filtering_to_fewer_than_two_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.sc.runtime import trainers

    dataset = SimpleNamespace(
        inspect=lambda _labels: SimpleNamespace(
            active_labels=("Scratch",),
            skipped_unreadable_samples=2,
        )
    )

    with pytest.raises(RuntimeExecutionError) as exc_info:
        trainers._inspect_training_dataset(
            cast(Any, dataset),
            ["Scratch", "Particle"],
        )

    assert exc_info.value.code == "sc_training_insufficient_labels_after_image_filter"
    assert exc_info.value.details == {
        "active_labels": ["Scratch"],
        "skipped_samples": 2,
    }
