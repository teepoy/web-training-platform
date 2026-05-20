# Runtime De-stubbing Implementation Plan

This plan tracks replacement of remaining scaffold/stub runtime behavior with working production paths.

## Progress

- [x] Phase 1 implemented
- [x] Phase 2 implemented
- [x] Phase 3 implemented
- [x] Phase 4 implemented
- [x] Phase 5 implemented
- [x] Phase 6 implemented
- [x] Phase 7 implemented
- [x] Phase 8 implemented
- [x] Phase 9 implemented
- [x] Phase 10 (docs updates in this file and API tests)

## Decisions locked in

- `clip-zero-shot-v1` is inference-only (non-trainable).
- Torch `embedding` target will be implemented with real penultimate-layer embeddings.

## Phase 1 — Preset capability gating

- Add first-class preset capability metadata (`trainable`).
- Mark inference-only presets as `trainable: false`.
- Reject training job creation for non-trainable presets with HTTP 422.
- Expose `trainable` in preset API payloads for frontend filtering.

Acceptance criteria:

- `GET /api/v1/training-presets/{id}` includes `trainable`.
- `POST /api/v1/training-jobs` returns 422 for inference-only presets.

## Phase 2 — Remove fake artifact success paths

- Remove placeholder fallback artifact URIs from Prefect engine.
- Ensure completed jobs require artifact metadata emitted by the execution path.
- Treat missing artifacts on completed jobs as failure/terminal error.
- Tighten artifact persistence validation so URI scheme alone does not imply existence.

Acceptance criteria:

- No completed job stores fabricated `s3://...` artifacts.
- Completed jobs without real artifacts do not remain marked successful.

## Phase 3 — Shared real training runner

- Extract a shared training runner used by Prefect flow and local engine.
- Remove default scaffold training loop from flow code.
- Standardize runner input/output contract around preset runtime dataclasses.

Acceptance criteria:

- Local and Prefect paths execute the same train dispatch logic.
- No default simulated epoch loop remains in production path.

## Phase 4 — Real Torch training

- Implement real `TorchTrainer` for classification presets.
- Build dataset/dataloader from repository samples and adapter output.
- Load images from `data:`, `memory://`, and `s3://`.
- Train/fine-tune model, persist checkpoint + metrics as artifacts.
- Emit model metadata needed for later prediction loading.

Acceptance criteria:

- Training returns a real checkpoint artifact URI and metrics artifact URI.
- Downloaded model artifact bytes are valid checkpoint data.

## Phase 5 — Real Torch prediction + embeddings

- Implement checkpoint loading in `TorchPredictor`.
- Implement real classification inference.
- Implement `embedding` target via penultimate-layer activations.
- Reject unsupported targets explicitly (no `not_implemented` payloads).

Acceptance criteria:

- Classification predictions come from loaded model inference.
- Embedding target returns deterministic vector output shape from model runtime.

## Phase 6 — CLIP zero-shot inference-only cleanup

- Keep CLIP prediction path via embedding service.
- Remove any train-time scaffolding language from preset/docs.
- Ensure frontend does not present non-trainable presets for job creation.

Acceptance criteria:

- `clip-zero-shot-v1` remains available for prediction, blocked for training.

## Phase 7 — Feature ops real computation

- Replace mock feature extraction and analytics with embedding-backed computation.
- Persist embeddings through repository feature tables.
- Implement real uniqueness/representativeness/hints from embedding neighborhoods/clusters.

Acceptance criteria:

- Feature ops endpoints return computed values derived from persisted embeddings.

## Phase 8 — Kubeflow real execution path

- Replace no-op Kubeflow train command with real worker command.
- Stop fake fallback IDs/events when cluster submit fails.
- Surface infrastructure failures as explicit submission errors.

Acceptance criteria:

- Submitted Kubeflow jobs execute real training runner entrypoint.
- Failure to submit is visible to API callers.

## Phase 9 — Frontend/API contract cleanup

- Remove or implement placeholder client methods (`getJobMetrics`).
- Align artifact download typing/handling with binary response behavior.
- Filter non-trainable presets out of train-job creation UI.

Acceptance criteria:

- No UI call references non-existent or placeholder training APIs.

## Phase 10 — Docs and smoke verification

- Remove mock/scaffold wording from architecture and README docs.
- Update API docs with trainability behavior and endpoint contracts.
- Run backend tests and smoke checklist after major phases.

Verification note:

- API tests now isolate SQLite state per test case and reset container singletons between runs. This avoids repeated FastAPI lifespan startup/shutdown races against a shared SQLite file while keeping the test profile lightweight.

Acceptance criteria:

- Docs describe only currently working runtime paths.
- Smoke checklist passes for training/prediction critical path.
