# API-Side Sync Worker Callsites Audit

> **Scope**: Every API-side callsite that invokes `predict_batch` or `embed_batch` via a worker
> client, **excluding** code under `**/flows/**` and `**/workers/**`.
>
> **Purpose**: Gate document for Scope B planning — determines whether any HTTP routes call
> worker methods synchronously in a way that is latency-sensitive and should be migrated to
> a job-based pattern.
>
> **Cross-reference**: See `docs/architecture/runtime-contract.md` for the worker protocol
> contract and `GpuWorker` / `InferenceWorker` protocol definitions.

---

## 1. Inventory

| File:Line | Method | HTTP Route(s) | Sync/Job | Recommendation |
|-----------|--------|---------------|----------|----------------|
| `apps/api/app/modules/prediction/app/services/prediction_service.py:496` | `_predict_via_worker` → `worker.predict_batch(...)` | `POST /predictions/run` (test-env branch only)<br>`POST /predictions/single` | **SYNC** — called directly in the request/response cycle when `_should_use_inference_worker()` is `True`. In production the `/predictions/run` route delegates to Prefect via `prediction_orchestrator.start_job()`; the sync path is only exercised in `test` env or via `/predictions/single`. | `POST /predictions/run`: **ALREADY-VIA-FLOW** in prod; sync path is test-only shim — `KEEP-SYNC` for test env.<br>`POST /predictions/single`: **MIGRATE-TO-JOB** — single-sample prediction is latency-sensitive and blocks the HTTP worker thread for the full model inference round-trip. |
| `apps/api/app/modules/datasets/app/services/feature_ops.py:135` | `extract_features_via_worker` → `worker.embed_batch(...)` | `POST /datasets/{dataset_id}/features/extract` (test-env branch only) | **SYNC** — called directly in the request/response cycle when `cfg.app.env == "test"`. In production the route delegates to Prefect via `prediction_orchestrator.start_job()`; `extract_features_via_worker` is only called from the Prefect flow (`predict_job.py`). | **ALREADY-VIA-FLOW** in prod; sync path is test-only shim — `KEEP-SYNC` for test env. |

### Classification of all 42 raw `rg` matches

The `rg -n "predict_batch|embed_batch" apps/api/app --glob '!**/flows/**' --glob '!**/workers/**'`
command returns 42 lines. They fall into these categories:

| Category | Count | Examples |
|----------|-------|---------|
| Protocol / interface definitions (`protocols.py`, `runtime.py`) | 6 | `InferenceWorker.predict_batch`, `GpuWorker.predict_batch`, `GpuWorker.embed_batch` |
| Concrete type implementations (not worker clients) | 3 | `clip.py:predict_batch`, `torch.py:predict_batch`, `sc/types/predictor.py:predict_batch` |
| **Actual worker-client callsites** (service layer) | **2** | `prediction_service.py:496`, `feature_ops.py:135` |
| Test files (`tests/`) | 31 | `test_prediction_flow.py`, `test_gpu_worker_client.py` |

Only the 2 service-layer callsites are in scope for this audit. All others are either
protocol definitions, local predictor implementations, or test code.

---

## 2. Recommendation per Route

### `POST /predictions/run`

**Classification: ALREADY-VIA-FLOW (production) / KEEP-SYNC (test env)**

In production (`dev`/`prod` profiles), this route immediately delegates to
`prediction_orchestrator.start_job()`, which schedules a Prefect flow. The
`prediction_service.run_prediction()` call — and therefore `_predict_via_worker` /
`worker.predict_batch` — is only reached inside the `if str(cfg.app.env) == "test":` branch.
This is an intentional test shim that allows integration tests to exercise the full prediction
pipeline without a live Prefect deployment.

**No Scope B action required** for this route. The production path is already async-via-flow.
The test shim should remain synchronous; converting it would break test isolation.

### `POST /predictions/single`

**Classification: MIGRATE-TO-JOB**

This route calls `prediction_service.predict_single()` unconditionally — there is no
`cfg.app.env == "test"` guard and no Prefect delegation. When `_should_use_inference_worker()`
returns `True` (i.e., a GPU or inference worker is configured, which is always the case in
`dev`/`prod`), the route blocks the HTTP worker thread for the full model inference round-trip
to the GPU worker service.

Depending on model size and batch complexity, this can take seconds to tens of seconds. This
is the only route that is genuinely sync-and-latency-sensitive in production.

**Scope B should address this route** by either:
1. Converting it to a job-based pattern (returns a job ID, client polls for result), or
2. Accepting the latency if the use-case is explicitly interactive (e.g., annotation assist
   where the user is waiting for a single-sample result).

### `POST /datasets/{dataset_id}/features/extract`

**Classification: ALREADY-VIA-FLOW (production) / KEEP-SYNC (test env)**

Identical pattern to `/predictions/run`. The `feature_ops.extract_features()` call (which
uses the embedding service, not the worker client) is inside the `if str(cfg.app.env) == "test":` guard.
The `extract_features_via_worker` method — which calls `worker.embed_batch` — is only invoked
from the Prefect flow (`predict_job.py`), not from any HTTP route handler.

**No Scope B action required** for this route.

---

## 3. Follow-up Scope B Trigger Criteria

Scope B (sync→async route migration) is justified if **any** of the following conditions hold:

1. **Observed latency breaches**: `POST /predictions/single` p95 latency exceeds 5 seconds in
   production load testing or real traffic. At that point the HTTP timeout risk outweighs the
   UX simplicity of a synchronous response.

2. **New sync callsites added**: A future PR adds a new HTTP route that calls `predict_batch`
   or `embed_batch` outside a `cfg.app.env == "test"` guard and outside a Prefect flow.

3. **Worker pool exhaustion**: The GPU worker service becomes a bottleneck because multiple
   concurrent `/predictions/single` requests hold open HTTP connections to it simultaneously.
   A job queue would serialize and back-pressure these requests gracefully.

4. **Client timeout complaints**: Frontend or SDK clients report `504 Gateway Timeout` errors
   on `/predictions/single` for large models (e.g., VQA with CLIP-ViT-Large).

If none of these conditions are met, Scope B is optional and can be deferred indefinitely.
The current architecture is correct for the scale it targets.

---

## Evidence

- `.sisyphus/evidence/task-1-audit-coverage.txt` — raw `rg` output (42 lines) with row-count reconciliation
- `.sisyphus/evidence/task-1-line-verify.txt` — confirms both `File:Line` entries in the table are non-empty

---

*Generated: 2026-05-26. Re-run `rg -n "predict_batch|embed_batch" apps/api/app --glob '!**/flows/**' --glob '!**/workers/**'` to verify coverage after any refactor.*
