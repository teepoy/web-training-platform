# API Endpoints (v1 scaffold)

## Datasets and annotation

- `POST /api/v1/datasets`
- `GET /api/v1/datasets`
- `POST /api/v1/datasets/{dataset_id}/samples`
- `GET /api/v1/datasets/{dataset_id}/samples`
- `POST /api/v1/annotations`

## Training presets and jobs

- `POST /api/v1/training-presets`
- `GET /api/v1/training-presets`
- `POST /api/v1/training-jobs`
- `GET /api/v1/training-jobs`
- `GET /api/v1/training-jobs/{job_id}`
- `POST /api/v1/training-jobs/{job_id}/cancel`
- `GET /api/v1/training-jobs/{job_id}/events` (SSE)
- `POST /api/v1/training-jobs/{job_id}/mark-left`

## Predictions and edits

- `POST /api/v1/predictions`
- `GET /api/v1/predictions`
- `PATCH /api/v1/predictions/{prediction_id}`

## Export and advanced sample-selection ops

- `GET /api/v1/exports/{dataset_id}`
- `POST /api/v1/exports/{dataset_id}/persist`
- `POST /api/v1/datasets/{dataset_id}/features/extract`
- `GET /api/v1/datasets/{dataset_id}/similarity/{sample_id}`
- `GET /api/v1/datasets/{dataset_id}/selection-metrics`
- `GET /api/v1/datasets/{dataset_id}/hints/uncovered`
