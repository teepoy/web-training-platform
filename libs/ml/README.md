# ML Library

Optional execution kernels for SC training and prediction.

This package owns direct imports of Torch, TorchVision, and Ultralytics. It
accepts plain image bytes and labels and returns plain checkpoints, metrics, and
prediction records. It must not import FastAPI application modules, Prefect,
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
