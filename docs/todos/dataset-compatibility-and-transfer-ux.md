# TODO: Dataset Compatibility and Transfer UX Hardening

## Baseline

- Recorded before implementation at commit `403d59030`.
- **Overall status:** Complete.
- Existing user data must remain usable. No backfill is required; compatibility
  must be handled when legacy resources are read or a feature must be hidden
  when its required capability genuinely cannot be reconstructed.

## Goal

Restore the Dataset detail, SC classify, sampling/export, and Model transfer
flows reported during live verification. UI placement and validation should
reflect the real transport contracts instead of exposing implementation-only
fields or errors.

## Reported Issues

1. Remove the eager `Please select a model` validation hint from the compatible
   Model picker. Selection remains required before submission.
2. Explain and restore compatibility for SC Global Filter statistics when a
   legacy Dataset lacks `dataset_meta.source_inspection_time`. Hide Global
   Filter only when the Dataset cannot supply a valid filter scope through any
   supported persisted identity.
3. Replace the generic Internal Server Error from Global Filter statistics with
   correct results or a specific capability/error response.
4. Place Dataset Import and Export actions in the Export sub-tab instead of the
   general Dataset header/action surface.
5. Restore sampling preparation from the Dataset Export sub-tab.
6. Restore SC classify map loading for existing Datasets without requiring a
   data backfill.
7. Make Model exports self-describing. Import must derive the artifact format
   and compatible training provenance from the exported package rather than
   asking the user for a Training job ID and Format.

## Investigation Contract

- Reproduce each server/UI symptom through a deterministic API or browser test
  before changing it.
- Inspect both named Datasets:
  `70dfcec3-4066-420d-80f7-e53f53718c67` and
  `fefd5b68-bb47-4679-bd74-73b80e5a5176`.
- Treat `storage_mode`, Dataset view contract, SC inspection identity, and
  portable transfer format as separate concerns.
- Preserve backward-compatible reads for all behavior other than settings and
  deployment configuration; do not introduce a migration or backfill solely
  to repair these flows.
- Keep legacy extra transfer fields ignorable.

## Acceptance Criteria

- The Model picker has no error-styled hint before a submission attempt.
- Global Filter statistics either load for compatible legacy SC Datasets or
  the Global Filter control is absent with no request/error noise when the
  capability is unavailable.
- Both named Dataset pages load without an Internal Server Error.
- Import and Export appear only in the Dataset Export sub-tab.
- Sampling preparation succeeds for the named Dataset and has a regression
  test at the failing seam.
- SC classify map loading succeeds for the named Dataset and remains based on
  platform sample/map identity rather than `defect_id`.
- A Model exported by the platform can be imported by choosing the package and
  a receiving name only; package metadata is integrity-checked and determines
  format/provenance compatibility.
- Lint, focused tests, backend tests/OpenAPI sync, frontend unit/build, and
  route-level E2E checks pass.

## Progress

- [x] Requested checkpoint committed at `403d59030`.
- [x] Goal and compatibility constraints recorded before implementation.
- [x] Exact failures reproduced and ranked hypotheses documented.
- [x] Dataset filter/classify compatibility repaired in the storage-mode
      materialization seam; the persisted-data integration regression covers filter
      statistics, sampling preparation/selection, and map-column reads.
- [x] Dataset Export sub-tab and sampling source failure repaired.
- [x] Model picker and self-describing transfer flow repaired.
- [x] Full verification complete.

## Reproduction and Decisions

- Dataset `70dfcec3-4066-420d-80f7-e53f53718c67` is `db_full`, has four
  complete persisted SC rows, and has no scalar source inspection in Dataset
  metadata. Its filter request failed with the reported missing
  `dataset_meta.source_inspection_time` error because the SC data provider was
  applying the identity-only sparse materialization path to every storage mode.
  Global Filter remains visible: persisted rows are a valid scope and now use
  platform sample IDs as row keys without contacting upstream.
- Dataset `fefd5b68-bb47-4679-bd74-73b80e5a5176` is
  `file_shard_sparse` and intentionally stores membership plus one exact source
  inspection identity. Its source inspection had disappeared from the upstream
  simulator; the gRPC `NOT_FOUND` escaped as an Internal Server Error. The
  historical inspection was republished through the external source API
  (not by writing platform data), and missing inspections now map to an explicit
  absent-source result rather than a 500.
- Filter statistics, classify/map, and Review Sampling all consume the same SC
  materialized data objects. Repairing source selection at that common seam
  avoids three separate fallbacks and preserves the `row_key` / `map_id`
  identity contract.
- Focused SC verification passes: `243 passed, 2 skipped`; the storage-mode
  regression exercises materialization through DuckDB for numeric filter
  statistics, the Export sampling-preparation aggregate, random sampling by
  `map_id`, and map data. Pyright reports zero errors for the SC module. Live
  ports were unavailable for the final concrete-page recheck, so the existing
  recorded HTTP evidence remains the live-environment signal.
- Product Model export is now a `platform.model-package` ZIP. Its versioned
  manifest owns training job ID, format, checksum, trainer, and model contract;
  product import asks only for the package and receiving name. The referenced
  job must already exist in the receiving organization. Existing raw artifact
  download/upload remains available for API compatibility.
- Final verification passes: diff-scoped lint; `1072` backend tests with `15`
  skips and one expected xpass; OpenAPI sync; `519` frontend unit tests; web
  production build; and `12` focused Dataset route E2E tests. The final live
  page recheck was unavailable to the automation worker, so that limitation is
  recorded rather than presented as live-browser evidence.
