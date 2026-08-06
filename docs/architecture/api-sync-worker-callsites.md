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

There are no API-side direct worker-client calls outside `**/flows/**` and
`**/workers/**`.

| HTTP route                 | Application boundary                          | Runtime behavior                                                                                 |
| -------------------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `POST /predictions/run`    | `PredictionExecutionPort.submit_job(command)` | Resolves catalog compatibility, persists a job, then submits the direct prediction deployment.   |
| `POST /predictions/single` | `PredictionRuntimePort.predict_single(...)`   | Resolves the predictor and waits synchronously for the same direct Prefect deployment to finish. |

### Classification of raw `rg` matches

The `rg -n "predict_batch|embed_batch" apps/api/app --glob '!**/flows/**' --glob '!**/workers/**'`
results fall into these categories:

| Category                                           | Examples                                                        |
| -------------------------------------------------- | --------------------------------------------------------------- |
| Protocol / interface definitions (`runtime.py`)    | `Predictor.predict_batch`                                       |
| Concrete type implementations (not worker clients) | SC predictor implementations under the current runtime boundary |
| Runtime flow implementations                       | `prediction/flows/**`                                           |
| Tests                                              | prediction flow and predictor tests                             |

---

## 2. Recommendation per Route

### `POST /predictions/run`

**Classification: ASYNC JOB**

The route converts its strict HTTP DTO into `PredictionJobCommand` and delegates to
`PredictionExecutionPort`. Dataset/model lookup, predictor compatibility, deployment
availability, job persistence, and Prefect submission are owned by
`PredictionSubmissionService` in that order. Configuration failures do not leave queued orphan jobs.

### `POST /predictions/single`

**Classification: MIGRATE-TO-JOB**

This route calls `PredictionRuntimePort.predict_single()` and waits for a Prefect flow to
complete. It no longer invokes a worker client or resolves deployment through capability
metadata: `PredictionRuntimeService` resolves the predictor from the model catalog and uses
the infrastructure-owned `PREDICTION_RUNTIME_DEPLOYMENT`; the application-layer submission
mapper converts `PredictionJobCommand` into the minimal Prefect parameters.

Depending on model size and batch complexity, this can take seconds to tens of seconds. This
is the only route that is genuinely sync-and-latency-sensitive in production.

**Scope B should address this route** by either:

1. Converting it to a job-based pattern (returns a job ID, client polls for result), or
2. Accepting the latency if the use-case is explicitly interactive and the user is waiting
   for a single-sample result.

## 3. Follow-up Scope B Trigger Criteria

Scope B (sync→async route migration) is justified if **any** of the following conditions hold:

1. **Observed latency breaches**: `POST /predictions/single` p95 latency exceeds 5 seconds in
   production load testing or real traffic. At that point the HTTP timeout risk outweighs the
   UX simplicity of a synchronous response.

2. **New sync callsites added**: A future PR adds a new HTTP route that calls executable
   predictor/worker code outside a Prefect flow.

3. **Worker pool exhaustion**: The GPU worker service becomes a bottleneck because multiple
   concurrent `/predictions/single` requests hold open HTTP connections to it simultaneously.
   A job queue would serialize and back-pressure these requests gracefully.

4. **Client timeout complaints**: Frontend or SDK clients report `504 Gateway Timeout` errors
   on `/predictions/single` for large models.

If none of these conditions are met, Scope B is optional and can be deferred indefinitely.
The current architecture is correct for the scale it targets.

---

## Evidence

- `apps/api/app/modules/prediction/app/services/submission_service.py`
- `apps/api/app/modules/prediction/app/services/prediction_runtime.py`
- `apps/api/app/modules/prediction/app/services/submission_parameters.py`
- `apps/api/app/modules/prediction/domain/submission.py`

---

_Updated: 2026-08-05. Re-run `rg -n "predict_batch|embed_batch" apps/api/app --glob '!**/flows/**' --glob '!**/workers/**'` to verify coverage after any refactor._
