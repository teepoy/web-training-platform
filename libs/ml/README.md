# ML Library

Optional model implementations for SC training and prediction.

This package owns direct imports of Torch, TorchVision, and Ultralytics. It
accepts private in-process datasets and value models and returns checkpoint
paths, metrics, and prediction records. It must not import FastAPI application modules, Prefect,
repositories, ORM models, or dependency-injection containers.

The dataclasses under `ml_library.models` are private, in-process value models—not
transport contracts. If SC execution moves across a process or language
boundary, define that interface in the existing `libs/protos` package,
preferably as protobuf and Arrow schema/manifest definitions.

Install it only for an SC GPU worker:

```bash
uv sync --package finetune-api --extra sc-runtime
```

The normal API and CPU worker environments intentionally omit this package.

## Dataset loading

The `ml_library.data_loading` namespace exposes three explicit loading modes;
callers choose the memory and shuffle semantics rather than going through a
factory:

- `collect_parquet_dataset(...)` collects small Parquet inputs into a Torch
  map-style dataset. `DataLoader(shuffle=True)` is supported.
- `open_hf_arrow_dataset(...)` memory-maps one pre-materialized Arrow IPC stream
  with Hugging Face `Dataset.from_file`. It rejects Parquet and does not create a
  Hugging Face cache. Install this mode with the `huggingface` extra. The caller
  must keep the Arrow file alive until the dataset and its workers are closed.
- `stream_parquet_dataset(...)` returns a Torch `IterableDataset` with
  row-group partitioning and bounded-memory shuffle. Use
  `DataLoader(shuffle=False)`; the dataset performs the shuffle itself.
- `ScTrainingDataset(...)` projects the streaming Parquet rows into valid SC
  `TrainingSample` values, records unreadable-image counts, preserves compact
  label order, and can be replayed without retaining all image bytes.
- `ScPredictionDataset(...)` projects row groups into `PredictionSample` values
  one row at a time. Missing images remain `None` so predictors can emit the
  established per-sample failure instead of aborting the stream.

Both Parquet modes generate `__row_index` from the explicit input path order and
physical row order. The Arrow mode requires the materializer to persist the same
integer column. None of the modes depends on a domain-specific `sample_id`.
