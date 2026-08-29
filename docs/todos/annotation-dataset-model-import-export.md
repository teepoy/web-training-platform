# TODO: Annotation, Dataset, and Model Import/Export

## Batch Baseline

- Recorded before implementation at commit
  `83db1c1d50242b4086978e07918d80b62c4f7785`.
- **Overall status:** Planned; no implementation from this batch has started.

## Requested Outcomes

- Implement import and export for annotations.
- Implement import and export for Datasets.
- Implement import and export for Models.

## Required Investigation

- Inventory current registered importers/exporters, SC prediction/KLARF export,
  Parquet/manual Dataset import, Label Studio synchronization, model upload and
  artifact download, existing route contracts, and capability matrices.
- Separate resource metadata portability from bulk data/artifact transfer.
- Define versioned portable manifests for Dataset, annotation, and Model facts;
  reuse existing OpenAPI, Arrow/Parquet, object-storage, and model-contract
  identities instead of inventing duplicate DTOs.
- Define how imports handle ownership, organization, creator, stable IDs,
  revisions/snapshots, label spaces, view/model contracts, storage modes,
  prediction provenance, duplicate names, and missing external artifacts.
- Route UI flows through registered descriptors plus `FlowModal` and
  `FlowTypeSelector`; do not hardcode format switches in resource pages.
- Keep large transfers streaming or object-reference based with explicit limits,
  cancellation, progress, checksum/integrity verification, and cleanup.

## Compatibility and Failure Rules

- Existing import/export and Label Studio flows remain backward-compatible.
- Import does not trust exported organization/user IDs or environment-specific
  URLs. The receiving organization and actor are established by authorization.
- Model import must validate the registered model contract and artifact integrity
  before publishing a usable Model.
- Dataset import must validate storage mode, view contract, schema, and label
  contract before publishing a revision.
- Annotation import must resolve stable sample identity and label mapping
  explicitly; unknown samples or labels are reported, not silently discarded.
- Partial import behavior, idempotency keys, overwrite/merge policy, and rollback
  boundary must be explicit per resource type.

## Acceptance Criteria

- Supported formats and capability descriptors are documented for annotations,
  Datasets, and Models.
- Each resource has a complete export/import round-trip test that preserves the
  approved portable facts and does not preserve environment-owned facts.
- Imports are authorization-scoped, idempotent under the approved policy, and
  produce clear validation and partial-failure reports.
- Large data/model artifacts are streamed or transferred by signed/object-store
  reference with bounded memory use.
- Resource revisions, model contracts, annotation provenance, checksums, and
  generated API artifacts remain consistent.
- Frontend flows, backend tests, OpenAPI sync, storage-mode capability tests, and
  relevant E2E tests pass.

## Open Decisions

- Required first formats for each resource (for example JSON/JSONL, Parquet,
  COCO/YOLO, Label Studio, portable ZIP, or native manifest).
- Whether Dataset export includes raw images by default, optionally, or only by
  explicit image-capable exporter.
- Annotation merge policy and unknown-sample/unknown-label behavior.
- Whether Model export/import targets native platform bundles only or also
  algorithm-specific formats such as Ultralytics checkpoints.
