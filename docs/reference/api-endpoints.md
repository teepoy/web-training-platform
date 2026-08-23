# API Endpoints

This is a high-level endpoint index for the current API surface. It is not a schema reference.

## Service health

- `GET /health` — Process liveness check. Returns `200 {"status":"ok"}` while the API process is serving requests; it does not check database connectivity.
- `GET /ready` — Database-backed readiness check. Executes a lightweight database query and returns `200 {"status":"ready"}` when the API can serve database-dependent traffic, or `503 {"status":"unavailable"}` when the database is unavailable.

## Datasets and annotation

- `POST /api/v1/datasets`
- `GET /api/v1/datasets` — Paginated list with optional server-side `q` and `creator_id` filters.
- `GET /api/v1/datasets/creators` — Creators available in the current organization's accessible dataset scope.
- `GET /api/v1/datasets/{dataset_id}`
- `POST /api/v1/datasets/{dataset_id}/samples`
- `POST /api/v1/datasets/{dataset_id}/samples/import` (bulk sample import via Label Studio `import_tasks`; each item may include optional `label`, and `null` means unlabeled task/sample)
- `GET /api/v1/datasets/{dataset_id}/samples`
- `GET /api/v1/datasets/{dataset_id}/samples/{sample_id}/images/{image_id}` — Serve an embedded sparse image from a dataset shard. Browser-native image callers must pass auth context by query parameter (`token`, and `org_id` when needed) because `<img>` requests cannot send platform headers.
- `GET /api/v1/images/resolve?uri=` — Resolve storage-backed image URIs such as `s3://...` or `memory://...` through the backend image proxy. Frontend code should call `resolveImageUri()` / `resolveImageUris()` instead of hand-building this URL.
- `GET /api/v1/datasets/{dataset_id}/annotation-stats` (aggregate annotation progress: total/annotated/unannotated counts and per-label distribution)
- `GET /api/v1/datasets/{dataset_id}/status` (dataset-level training gate: `allow_train`, active/minimum class counts, and a machine-readable disable reason)
- `POST /api/v1/annotations`
- `POST /api/v1/datasets/{dataset_id}/annotations/bulk-sc` — Sparse SC bulk annotation using defect IDs and the dataset manifest sample index.

## Models

- `GET /api/v1/models` — Paginated list with optional server-side `q`, `creator_id`, `dataset_id`, and `job_id` filters.
- `GET /api/v1/models/creators` — Creators available in the current organization's accessible model scope.
- `GET /api/v1/models/{model_id}`
- `PATCH /api/v1/models/{model_id}`
- `DELETE /api/v1/models/{model_id}`

## SC inspection and image endpoints

- `GET /api/v1/sc/inspections`
- `GET /api/v1/sc/inspections/{inspection_time}/{wafer_key}/samples`
- `POST /api/v1/sc/inspections/{inspection_time}/{wafer_key}/box-filter`
- `POST /api/v1/sc/datasets/{dataset_id}/box-filter`
- `GET /api/v1/sc/images/{inspection_time}/{wafer_key}/{defect_id}/{image_type}` — Web-gateway alias forwarded directly to image-parser `/sc/images/...`; FastAPI does not register this route or provide a bytes fallback. Supported frontend aliases include `template`, `defective`, `difference`, and review variants.
- `GET /api/v1/sc/sprites/{mode}/{inspection_time}/{wafer_key}/{defect_id}` — Web-gateway alias forwarded directly to image-parser `/sc/sprites/...` for the current per-defect sprite contract.
- `GET /api/v1/sc/inspections/{inspection_time}/{wafer_key}/image-profile` — Web-gateway alias forwarded directly to image-parser. Returns all Patch instances plus native 8/12/16-bit observed ranges for Gallery/Colors Settings; FastAPI has no proxy route.
- `POST /api/v1/sc/gallery-downloads` — Web-gateway alias forwarded directly to image-parser. It accepts an explicit Gallery selection as a bounded form payload, prepares the ZIP on the Export lane, and streams the completed attachment without a FastAPI or browser-Blob proxy.
- `/api/v1/sc/sprite-atlases/...` is not a current API contract. If an atlas contract is introduced, atlas generation and HTTP serving belong to image-parser and the web gateway must forward it directly; do not add a Python image-bytes proxy or fallback.
- Imported SC dataset views emit the same scalar-identity image-parser URLs as preview. The web client appends browser authentication before rendering. FastAPI does not expose a Dataset-owned SC image-bytes route.
- `POST /api/v1/sc/import`

## Authentication and org context

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login` (returns a JWT access token; default expiry is 60 minutes via backend config)
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/tokens`
- `GET /api/v1/auth/tokens`
- `DELETE /api/v1/auth/tokens/{token_id}`

## Training presets and jobs

- `GET /api/v1/training-presets`
- `GET /api/v1/training-presets/{preset_id}`
- `POST /api/v1/training-jobs`
- `GET /api/v1/training-jobs`
- `GET /api/v1/training-jobs/{job_id}`
- `POST /api/v1/training-jobs/{job_id}/cancel`
- `GET /api/v1/training-jobs/{job_id}/events` (SSE)
- `POST /api/v1/training-jobs/{job_id}/mark-left`

## Prediction

- `POST /api/v1/predictions/run` (supports `target` and optional `prompt`)
- `POST /api/v1/predictions/single` (supports `target` and optional `prompt`)
- `GET /api/v1/samples/{sample_id}/predictions` (platform prediction rows, optional `model_version` filter)
- `GET /api/v1/prediction-jobs/{job_id}/predictions`
- `POST /api/v1/prediction-collections` — Create a named platform prediction collection
- `GET /api/v1/prediction-collections?dataset_id=` — List prediction collections for a dataset
- `POST /api/v1/prediction-collections/{collection_id}/sync-label-studio` — Materialize a collection into the dataset's LS project with a sync tag

## Schedules and dashboard

- `GET /api/v1/dashboard`
- `GET /api/v1/schedules/capabilities` — List explicitly registered executable schedule targets
- `POST /api/v1/schedules`
- `GET /api/v1/schedules`
- `GET /api/v1/schedules/{schedule_id}`
- `PATCH /api/v1/schedules/{schedule_id}`
- `DELETE /api/v1/schedules/{schedule_id}`
- `POST /api/v1/schedules/{schedule_id}/run`
- `POST /api/v1/schedules/{schedule_id}/pause`
- `POST /api/v1/schedules/{schedule_id}/resume`
- `GET /api/v1/schedules/{schedule_id}/runs`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/runs/{run_id}/logs`

## Agent and display surfaces

- `GET /api/v1/sessions/{session_id}/surfaces/{surface_id}` — Get current surface state
- `POST /api/v1/sessions/{session_id}/surfaces/{surface_id}/panels` — Add or replace a panel
- `DELETE /api/v1/sessions/{session_id}/surfaces/{surface_id}/panels/{panel_id}` — Remove a panel
- `GET /api/v1/sessions/{session_id}/surfaces/{surface_id}/export` — Export surface state document
- `POST /api/v1/sessions/{session_id}/surfaces/{surface_id}/import` — Import surface state document
- `POST /api/v1/datasets/{dataset_id}/query` — Structured data query (annotation-stats, sample-slice, metadata-histogram, recent-annotations, prediction-summary)
- `POST /api/v1/datasets/{dataset_id}/agent/chat` — Agent chat (SSE stream response)

## Export and similarity ops

- `GET /api/v1/exports/{dataset_id}`
- `POST /api/v1/exports/{dataset_id}/persist`
- `POST /api/v1/sc/datasets/{dataset_id}/prediction-exports/stream` — Export Annotation, Prediction, or Final Class SC results as KLARF 1.2/1.8, Parquet, or ZIP, optionally with ordered Review Sampling and Extra Filter
- `POST /api/v1/sc/dataset-collections/{collection_id}/prediction-exports/stream` — Export selected linked Dataset records; Parquet stays combined and the selected KLARF version is split into complete numbered files by inspection
- `GET /api/v1/datasets/{dataset_id}/similarity/{sample_id}`

## Prediction review and annotation versioning

- `POST /api/v1/prediction-reviews` — Create a review action (requires `dataset_id`, `model_id`, optional `model_version`, optional `collection_id`, optional `sync_tag`)
- `GET /api/v1/prediction-reviews?dataset_id=` — List review actions for a dataset
- `GET /api/v1/prediction-reviews/{action_id}` — Get a single review action
- `DELETE /api/v1/prediction-reviews/{action_id}` — Delete a review action (cascades to annotation versions)
- `POST /api/v1/prediction-reviews/{action_id}/annotations` — Save reviewed predictions as annotations using platform `prediction_id` provenance
- `GET /api/v1/prediction-reviews/{action_id}/annotation-versions` — List annotation versions for a review action
- `GET /api/v1/export-formats` — List available export format IDs
- `GET /api/v1/prediction-reviews/{action_id}/export?format_id=` — Preview annotation version export as JSON
- `POST /api/v1/prediction-reviews/{action_id}/export/persist` — Persist export to artifact storage
