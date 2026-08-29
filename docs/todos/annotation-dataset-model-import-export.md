# TODO: Annotation, Dataset, and Model Import/Export

## Batch Baseline

- Recorded before implementation at commit
  `83db1c1d50242b4086978e07918d80b62c4f7785`.
- **Overall status:** Complete.

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

## Implemented Contract

- Dataset: registered JSON/manual/Parquet imports and Parquet export. Parquet
  preserves a dedicated platform `sample_id`, latest label, metadata, and image
  references without embedding raw images. Legacy Parquet without IDs remains
  accepted and receives new IDs. Explicit duplicate/conflicting IDs fail before
  Label Studio or Dataset writes.
- Annotation: registered version-1 JSONL import/export keyed only by platform
  `sample_id`. The header carries the Dataset type/task/label-space contract.
  Import replaces only provided samples, null clears a provided annotation, and
  omitted samples are untouched. Unknown samples/labels, duplicate IDs, contract
  mismatch, byte overflow, and row overflow fail before writes.
- Model: registered artifact upload/download. Import must attach to an existing
  training job owned by the actor; the registered trainer validates its model
  contract and the server records artifact SHA-256 before publication. Export
  streams the immutable stored artifact.
- Receiving organization and actor always come from authorization. No exported
  ownership facts or environment URLs are trusted.
- Dataset export is page-to-Parquet-to-object-store streaming. Parquet imports
  use the upload spool and tracked YAML byte/row limits. Annotation export is
  paged; annotation import is byte/record bounded and writes fixed-size batches.
  Model downloads stream from object storage.
- Annotation replay is idempotent under `replace_provided`. Validation is
  all-before-write; if storage fails after batching starts, completed batches may
  remain and replaying the same file is the recovery operation. Dataset imports
  reject existing explicit IDs, so users must resolve a conflict instead of
  silently duplicating rows. Model upload creates one immutable artifact record.

## Verification Record

- Focused annotation, Parquet round-trip/sample-identity, and Model route/upload
  tests: 64 passed with one pre-existing skip.
- Full API suite and OpenAPI sync: 1,055 passed, 15 skipped, one expected pass;
  OpenAPI is in sync.
- Backend Ruff and Pyright: clean.
- Frontend: 101 test files / 523 tests passed; production build passed.
