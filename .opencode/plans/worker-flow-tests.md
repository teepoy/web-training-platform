# Worker-Side Flow Function Tests

**Goal**: Add direct unit tests for the code that runs inside Prefect workers — `run_training_pipeline()`, `run_prediction_job()`, and chunk tasks — to catch the recurring crashes in training and prediction features.
**Created:** 2026-04-19
**Status:** DONE

---

## TODOs

- [ ] T1: Add `_mock_inference_worker` autouse fixture to `apps/api/tests/conftest.py`
  - Same pattern as `_mock_embedding_service` and `_mock_ls_client`
  - Override `container.inference_worker` with a MagicMock that has:
    - `predict_batch` → returns `[{"sample_id": sid, "label": label_space[0], "confidence": 0.9, "scores": {...}}]` for each sample
    - `embed_batch` → returns `[{"sample_id": sid, "embedding": [0.1, 0.2, 0.3, 0.4]}]` for each sample
  - Opt-out via `no_inference_override` marker

- [ ] T2: Create `apps/api/tests/test_training_runner.py` — tests for `run_training_pipeline()`
  - Helper: `_seed_dataset_with_samples(client)` — creates dataset + N samples with data URIs + annotations via API, returns `(dataset_id, sample_ids)`
  - Test 1: `test_run_training_pipeline_completes` — seed dataset with 5 labeled samples, call `run_training_pipeline(job_id, dataset_id, "resnet50-cls-v1", artifact_storage=InMemoryArtifactStorage())`, assert status=completed, artifacts non-empty
  - Test 2: `test_run_training_pipeline_missing_dataset` — call with nonexistent dataset_id, assert `ValueError("Dataset not found")`
  - Test 3: `test_run_training_pipeline_missing_preset` — seed dataset, call with bad preset_id, assert `ValueError("Preset not found")`
  - Test 4: `test_run_training_pipeline_empty_dataset` — seed dataset with 0 samples, call pipeline, verify it completes (or raises meaningfully — current behavior TBD)
  - Test 5: `test_run_training_pipeline_persists_artifacts` — verify artifacts are written to the repository after completion
  - Note: Each test must use `TestClient(app)` context for DB table creation, then call `run_training_pipeline` via `asyncio.run()`

- [ ] T3: Create `apps/api/tests/test_prediction_flow.py` — tests for `run_prediction_job()` and chunk tasks
  - Helper: `_seed_prediction_setup(client)` — creates dataset + samples + model (via upload or direct DB), returns `(dataset_id, model_id, sample_ids, org_id)`
  - Test 1: `test_run_prediction_job_classification` — seed data, create a prediction job record in DB, call `run_prediction_job(job_id, dataset_id, model_id, org_id, target="image_classification")`, assert status updated to COMPLETED, predictions persisted
  - Test 2: `test_run_prediction_job_embedding_target` — same but `target="embedding"`, verify embedding extraction path
  - Test 3: `test_run_prediction_job_missing_dataset` — nonexistent dataset, assert `ValueError`
  - Test 4: `test_run_prediction_job_specific_sample_ids` — pass explicit `sample_ids` subset, verify only those processed
  - Test 5: `test_predict_chunk_missing_model` — call `predict_chunk` with bad model_id, assert `ValueError`
  - Test 6: `test_persist_chunk_results_writes_predictions` — call `persist_chunk_results` directly, verify predictions + events written to DB
  - Note: Must mock inference worker via container override. The `predict_job.py` tasks create their own `Container()`, so the conftest autouse mock must work for fresh containers too — verify this works or patch at module level if needed.

- [ ] T4: Add service boundary testing rule to root `AGENTS.md`
  - Under `## CONVENTIONS` or new `## SERVICE BOUNDARY TESTING`, add:
    ```
    - Every external-service boundary (Prefect, inference worker, embedding gRPC, LLM) must have a corresponding autouse mock fixture in `apps/api/tests/conftest.py`.
    - Worker-side flow functions (`apps/api/app/flows/`, `apps/api/app/runtime/`) must have direct unit tests that call them as plain Python with a real test DB and mocked external services.
    - When adding a new external service integration, add the mock fixture FIRST, then write the flow/service code.
    ```

- [ ] T5: Run `make test` and fix any failures

---

## Verification

- [ ] V0: `make test` passes with all new + existing tests
- [ ] V1: `test_training_runner.py` tests pass — `run_training_pipeline` exercises real DB + preset loading + trainer invocation
- [ ] V2: `test_prediction_flow.py` tests pass — `run_prediction_job` exercises real DB + container wiring + mocked inference

---

## Key Constraints

- Tests must NOT require a running Prefect server — call flow functions directly as async Python
- Tests must use the existing test config (SQLite + memory storage)
- The `_mock_inference_worker` fixture must work for `Container()` instances created inside flow tasks (predict_job.py creates fresh containers) — if `conftest` autouse doesn't propagate, use `monkeypatch` on the container class or module-level patching
- Follow existing test patterns: `from __future__ import annotations`, `TestClient(app)` context, inline setup
- Use `PRESET_ID = "resnet50-cls-v1"` from conftest for training tests
