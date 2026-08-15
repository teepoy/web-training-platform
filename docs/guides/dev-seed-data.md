# Development showcase data

Use `make seed-dev` after the development stack is healthy. The command creates
a moderate, deterministic showcase instead of the historical 300,000-row wafer
fixture. It is intended for exercising management pages, not for performance
benchmarks.

## Default contents

| Area                    | Development fixtures                                                                                                                                                 |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Datasets                | 180 labeled classification samples, 96 mixed labeled/unlabeled multi-image samples, one empty classification dataset, and one 2,500-row sparse SC inspection dataset |
| SC annotations          | Labels on the first 96 SC samples, spread across three classes                                                                                                       |
| Collections             | A two-dataset classification collection and a one-dataset SC collection, each with a ready pinned revision                                                           |
| Training and prediction | Four training jobs and four prediction jobs covering completed, failed, and cancelled states, with event histories                                                   |
| Models                  | Two metadata-only JSON model display fixtures plus metrics artifacts                                                                                                 |
| Schedules               | Two paused dataset-export schedules                                                                                                                                  |
| Sensors                 | Four disabled subscriptions covering dataset-size and timer sensors for train and predict workflows                                                                  |

The model fixtures have `seed_fixture: true` and `runnable: false` metadata and
are named as display fixtures. The seeded jobs have no external execution IDs.
`seed-dev` does not submit training or prediction jobs, run a schedule, or enable
a sensor subscription.

## Repeatability

The SC upstream fixture uses the fixed inspection time
`2026-08-01T04:00:00`. A matching SQLite fixture is reused, including its
inspection identity, so running the command on another day does not invalidate
the imported sparse dataset. Fixed dataset names and activity IDs are reused;
owned event rows are replaced instead of duplicated. Existing classification
samples are only topped up to the requested count and are never deleted.

If a fixed showcase name already belongs to an incompatible dataset type,
storage mode, collection view, or unrelated collection members, the seed stops
with an explicit error instead of changing that data.

## Adjusting the size

Override Make variables when a different local scale is useful:

```bash
make seed-dev \
  SC_WAFER_MOCK_DEFECTS=5000 \
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
