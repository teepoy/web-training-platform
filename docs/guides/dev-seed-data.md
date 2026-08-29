# Development showcase data

Use `make seed-dev` after the development stack is healthy. The command creates
a moderate, deterministic showcase instead of the historical 300,000-row wafer
fixture. It is intended for exercising management pages, not for performance
benchmarks.

All seed and synthetic-data implementations live under
`devtools/seedmaker/`. The compatibility entrypoints under `scripts/` contain
only thin forwarding code so production application and service packages do
not own development data generation.

## Default contents

| Area                    | Development fixtures                                                                                                                                                 |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Datasets                | 180 labeled classification samples, 96 mixed labeled/unlabeled multi-image samples, one empty classification dataset, and one 2,500-row sparse SC inspection dataset |
| SC annotations          | Labels on the first 96 SC samples, spread across three classes                                                                                                       |
| Collections             | A two-dataset classification collection and a one-dataset SC collection with saved snapshots, plus one empty dynamic SC Collection for automation tests              |
| Training and prediction | Four training jobs and four prediction jobs covering completed, failed, and cancelled states, with event histories                                                   |
| Models                  | Two metadata-only JSON model display fixtures plus metrics artifacts                                                                                                 |
| Membership automation   | One manual-only SC rule with a typed `defects >= 1` condition, a 10-record run cap, and a 2,500-row per-Dataset import cap                                           |
| Legacy execution data   | Two paused schedules and four disabled sensor subscriptions retained for backend compatibility tests; they are not ordinary-user navigation                          |
| Gallery profile VQA     | Three 64-defect inspections: Gray8 1R/1D/1M, Gray16 1R/1D/1M, and Gray16 2R/2D/1M; each has eight square Review images                                               |

The model fixtures have `seed_fixture: true` and `runnable: false` metadata and
are named as display fixtures. The seeded jobs have no external execution IDs.
`seed-dev` does not run the membership rule, submit training or prediction jobs,
run a schedule, or enable a sensor subscription. The dynamic Collection stays
empty until a developer explicitly previews and starts Discovery or Backfill.

## Repeatability

The SC upstream fixture uses the fixed inspection time
`2026-08-01T04:00:00`. A matching SQLite fixture is reused, including its
inspection identity, so running the command on another day does not invalidate
the imported sparse dataset. Fixed dataset, Collection, connector, rule, and
activity names are reused;
owned event rows are replaced instead of duplicated. Existing classification
samples are only topped up to the requested count and are never deleted.

The gallery fixtures share that timestamp and use stable wafer keys and names:
`81 / GRAY8-1R1D`, `82 / GRAY16-1R1D`, and `83 / GRAY16-2R2D`. Re-running the
seed replaces only those three inspection identities and their patch archives.
The baseline 12-bit inspection at wafer key `1` remains available.

If a fixed showcase name already belongs to an incompatible dataset type,
storage mode, collection view, or unrelated collection members, the seed stops
with an explicit error instead of changing that data.

## Adjusting the size

Override Make variables when a different local scale is useful:

```bash
make seed-dev \
  SC_WAFER_MOCK_DEFECTS=5000 \
  SC_GALLERY_PROFILE_DEFECTS=128 \
  SC_GALLERY_PROFILE_IMAGED=16 \
  DEV_SEED_CLASSIFICATION_SAMPLES=300 \
  DEV_SEED_REVIEW_SAMPLES=150 \
  DEV_SEED_SC_ANNOTATIONS=180
```

Lowering a classification count does not trim an existing dataset. Sparse SC
imports are immutable, so changing `SC_WAFER_MOCK_DEFECTS` after the first seed
stops with an explicit size mismatch; remove only the named SC showcase fixtures
before resizing. Changing
`SC_WAFER_MOCK_INSPECTION_TIME` intentionally changes the upstream inspection
identity; remove only the named `Dev SC Inspection` showcase fixtures before
doing that. Use the separate SC benchmark procedures when a 300,000-row dataset
is required.

## Runtime data-path benchmark

After `make up-dev` and `make seed-dev`, run:

```bash
make benchmark-sc-runtime-data-paths
```

This benchmark clones the seeded SC inspection into a temporary Dataset, labels
every imported row, and invokes the same Runtime callables used by the Prefect
worker. Training and Prediction open their distinct image-parser gRPC streams;
the service owns equipment dispatch, source download, cache reuse, and parsing.
Training then uses the Parquet materializer, while Prediction feeds its bounded
preprocessing stream and prediction writeback.
Only the GPU Trainer and Predictor kernels are replaced: the fake Trainer reads
every Parquet row and the fake Predictor consumes every resolved image pair.
The temporary Dataset and fake model artifact are removed after the run.

The JSON result reports setup time separately from training materialization and
prediction Runtime throughput. The local target enforces the established 3,000
samples/second prediction requirement; this hardware-sensitive benchmark is not
part of shared CI. The training threshold and either local threshold can be
overridden explicitly:

```bash
make benchmark-sc-runtime-data-paths \
  SC_RUNTIME_BENCHMARK_SAMPLES=50000 \
  SC_RUNTIME_BENCHMARK_MIN_TRAIN_SPS=500 \
  SC_RUNTIME_BENCHMARK_MIN_PREDICT_SPS=3000
```

The requested count is exact: the command fails instead of silently measuring
a smaller upstream fixture. For steady-state throughput measurements use at
least 50,000 rows; the default 2,500-row showcase fixture is intended for UI
development, not performance characterization.
