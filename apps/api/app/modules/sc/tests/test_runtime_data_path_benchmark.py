from __future__ import annotations

from collections.abc import AsyncIterator

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from benchmarks.sc_runtime_kernels import (
    fake_predict_yolo_stream,
    fake_train_yolo,
)


@pytest.mark.asyncio
async def test_fake_trainer_consumes_every_materialized_row(tmp_path) -> None:
    parquet_path = tmp_path / "training.parquet"
    pq.write_table(
        pa.table(
            {
                "sample_id": ["sample-1", "sample-2", "sample-3"],
                "label": ["scratch", "particle", "scratch"],
                "patch_defective_bytes": [b"d1", b"d2", b"d3"],
                "patch_template_bytes": [b"t1", b"t2", b"t3"],
            }
        ),
        parquet_path,
    )

    output = await fake_train_yolo(
        (parquet_path,),
        ("scratch", "particle"),
        valid_samples=3,
        work_dir=tmp_path / "work",
        shuffle_seed=17,
    )

    assert output.checkpoint_path.read_bytes() == b"fake-sc-training-checkpoint\n"
    assert output.metrics["benchmark_kernel"] == "fake"
    assert output.metrics["num_samples"] == 3
    assert output.metrics["num_classes"] == 2
    input_bytes = output.metrics["input_bytes"]
    assert isinstance(input_bytes, int)
    assert input_bytes > 0
    assert output.metadata["trained_samples"] == 3
    assert output.metadata["label_space"] == ["scratch", "particle"]


@pytest.mark.asyncio
async def test_fake_trainer_rejects_partial_materialized_input(tmp_path) -> None:
    parquet_path = tmp_path / "training.parquet"
    pq.write_table(
        pa.table(
            {
                "sample_id": ["sample-1", "sample-2"],
                "label": ["scratch", "particle"],
                "patch_defective_bytes": [b"d1", b"d2"],
                "patch_template_bytes": [b"t1", b"t2"],
            }
        ),
        parquet_path,
    )

    with pytest.raises(RuntimeError, match="expected 3 rows, consumed 2"):
        await fake_train_yolo(
            (parquet_path,),
            ("scratch", "particle"),
            valid_samples=3,
            work_dir=tmp_path / "work",
            shuffle_seed=17,
        )


@pytest.mark.asyncio
async def test_fake_predictor_preserves_order_and_consumes_item_errors(
    tmp_path,
) -> None:
    async def samples() -> AsyncIterator[dict[str, object]]:
        yield {
            "sample_id": "sample-1",
            "patch_defective_bytes": b"defective",
            "patch_template_bytes": b"template",
        }
        yield {
            "sample_id": "sample-2",
            "patch_defective_bytes": None,
            "patch_template_bytes": None,
            "error": "archive missing",
        }

    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"not-used")
    outputs = [
        output
        async for output in fake_predict_yolo_stream(
            checkpoint,
            ("scratch", "particle"),
            samples(),
        )
    ]

    assert [output.sample_id for output in outputs] == ["sample-1", "sample-2"]
    assert outputs[0].label == "scratch"
    assert outputs[0].confidence == 1.0
    assert outputs[0].scores == {"scratch": 1.0, "particle": 0.0}
    assert outputs[0].error is None
    assert outputs[1].error == "archive missing"
