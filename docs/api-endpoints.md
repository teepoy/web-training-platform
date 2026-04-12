# API Endpoints

This is a high-level endpoint index for the current API surface. It is not a schema reference.

## Datasets and annotation

- `POST /api/v1/datasets`
- `GET /api/v1/datasets`
- `GET /api/v1/datasets/{dataset_id}`
- `POST /api/v1/datasets/{dataset_id}/samples`
- `POST /api/v1/datasets/{dataset_id}/samples/import` (bulk sample import via Label Studio `import_tasks`; each item may include optional `label`, and `null` means unlabeled task/sample)
- `POST /api/v1/datasets/{dataset_id}/samples/import-vqa` (JSONL bulk import for VQA datasets)
- `GET /api/v1/datasets/{dataset_id}/samples`
- `GET /api/v1/datasets/{dataset_id}/annotation-stats` (aggregate annotation progress: total/annotated/unannotated counts and per-label distribution)
- `POST /api/v1/annotations`

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

## Export and advanced sample-selection ops

- `GET /api/v1/exports/{dataset_id}`
- `POST /api/v1/exports/{dataset_id}/persist`
- `POST /api/v1/datasets/{dataset_id}/features/extract`
- `GET /api/v1/datasets/{dataset_id}/similarity/{sample_id}`
- `GET /api/v1/datasets/{dataset_id}/selection-metrics`
- `GET /api/v1/datasets/{dataset_id}/hints/uncovered`

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
