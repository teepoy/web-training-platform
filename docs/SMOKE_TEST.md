# Smoke Test Checklist

Run this checklist after making significant changes to verify core functionality.

## Prerequisites

```bash
# Start the full stack, or use `make updev` for compose backend + local Vite
make up

# Wait for all services to be healthy
docker compose -f infra/compose/docker-compose.yaml ps
```

Services should be running:
- `compose-api-1` - API server (port 8000)
- `compose-web-1` - Web frontend (port 5173, only when using `make up`)
- `compose-postgres-1` - PostgreSQL (port 5432)
- `compose-minio-1` - MinIO storage (ports 9000, 9001)
- `compose-prefect-server-1` - Prefect server (port 4200)
- `compose-label-studio-1` - Label Studio (port 8080)
- `compose-training-worker-gpu-1` - GPU delegated worker
- `compose-training-worker-dspy-1` - DSPy delegated worker
- `compose-embedding-1` - Embedding service (port 50051)
- `compose-inference-worker-1` - HTTP inference service (port 8010)

When using `make updev`, expect the frontend to run as a local Vite process on
`:5173` instead of `compose-web-1`.

## 1. Authentication

### 1.1 Registration
- [ ] Navigate to http://localhost:5173/register
- [ ] Register a new user with name, email, password
- [ ] Verify redirect to datasets page after registration

### 1.2 Login
- [ ] Navigate to http://localhost:5173/login
- [ ] Login with registered credentials
- [ ] Verify redirect to datasets page
- [ ] Verify user avatar appears in header
- [ ] Refresh the page on a protected route and verify the session stays logged in
- [ ] Wait less than 60 minutes, refresh again, and verify the session is still valid

### 1.3 Logout
- [ ] Click avatar dropdown → Logout
- [ ] Verify redirect to login page
- [ ] Verify protected routes redirect to login

## 2. Datasets

### 2.1 Create Dataset
- [ ] Navigate to http://localhost:5173/datasets
- [ ] Click "New Dataset" button
- [ ] Enter dataset name
- [ ] Add initial labels (e.g., "cat", "dog")
- [ ] Submit and verify dataset appears in list
- [ ] Verify Label Studio project link works

### 2.2 View Dataset
- [ ] Click on a dataset to view details
- [ ] Verify samples list loads (may be empty)
- [ ] Verify Label Studio iframe or link is accessible

### 2.3 Add Labels
- [ ] In dataset detail or classify view, add a new label
- [ ] Verify label appears in label space

## 3. Samples

### 3.1 Create Sample
- [ ] In dataset detail view, create a new sample
- [ ] Upload or provide image URI
- [ ] Verify sample appears in list

### 3.2 Annotate Sample
- [ ] Navigate to classify view for a dataset
- [ ] Select a sample
- [ ] Apply a label annotation
- [ ] Verify annotation is saved

### 3.3 Classify Sidebar Wafer Map
- [ ] Open a dataset whose samples include numeric `metadata.wafer_x` and `metadata.wafer_y`
- [ ] Verify the `Wafer Map` panel appears in the classify sidebar and renders points
- [ ] Click one point and verify the `Selected Samples` panel shows the linked sample preview
- [ ] Cmd/Ctrl-click additional points and verify linked filtering reflects the toggled selection set
- [ ] Brush-select a region and verify sidebar selection expands
- [ ] Click `Clear` in the wafer map panel and verify the linked sample preview resets

## 3.4 Dataset Detail Wafer Map
- [ ] Navigate to the dataset detail page for a wafer dataset
- [ ] Verify the `Wafer Map` panel appears in the sidebar and renders points
- [ ] Verify selection emission is disabled (dataset browsing is read-only)

## 3.5 Remote Preview Wafer Map
- [ ] Launch a preview session (e.g., via `PreviewLaunchView.vue`) for data with wafer metadata
- [ ] Verify the `Wafer Map` panel appears in the preview workspace
- [ ] Verify points are rendered from session-loaded metadata (no dataset ID required)
- [ ] If no wafer metadata is present, verify the panel shows "No wafer points" empty state

## 4. Training Presets

### 4.1 List Presets
- [ ] Navigate to http://localhost:5173/presets
- [ ] Verify presets are listed as read-only catalog entries (no create/edit controls)

## 5. Training Jobs

### 5.1 Create Job
- [ ] Navigate to http://localhost:5173/jobs
- [ ] Click "New Job"
- [ ] Select dataset and preset
- [ ] Submit job
- [ ] Verify job appears in list with "queued" status

### 5.2 Monitor Job
- [ ] Click on a job to view details
- [ ] Verify SSE connection status shows "open" (not "error")
- [ ] Verify events stream as job progresses
- [ ] Verify the Training Progress card shows real metrics content for the job
- [ ] If the runtime emits only aggregate metrics, verify summary stats render from the `metrics` artifact instead of showing an empty placeholder
- [ ] If the runtime emits epoch/loss events, verify the line chart updates

### 5.3 Job Completion
- [ ] Wait for job to complete or fail
- [ ] Verify final status is reflected
- [ ] Check artifacts list if job completed

## 6. Schedules

### 6.1 List Schedules
- [ ] Navigate to http://localhost:5173/schedules
- [ ] Verify schedule list loads

### 6.2 Create Schedule
- [ ] Click "New Schedule"
- [ ] Configure cron expression and flow
- [ ] Submit schedule
- [ ] Verify schedule appears in list

### 6.3 Schedule Operations
- [ ] Pause a schedule
- [ ] Resume a schedule
- [ ] Trigger manual run
- [ ] View schedule runs

## 7. Label Studio Integration

### 7.1 Project Access
- [ ] From dataset detail, click Label Studio link
- [ ] Verify Label Studio opens with correct project
- [ ] Verify URL is external (localhost:8080), not internal Docker URL

### 7.2 Sync
- [ ] Create annotations in Label Studio
- [ ] Sync annotations back to platform
- [ ] Verify annotations appear in platform

## 8. VQA Runtime (DSPy)

- [ ] Set `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` for API runtime
- [ ] Create dataset with `dataset_type: "image_vqa"` and `task_type: "vqa"`
- [ ] Import VQA samples via `POST /api/v1/datasets/{dataset_id}/samples/import-vqa`
- [ ] Create training job with preset `dspy-vqa-v1`
- [ ] Wait for completion and verify model artifact `optimized_program.json` exists
- [ ] Call `POST /api/v1/predictions/single` with `target: "vqa"` and `prompt`
- [ ] Verify the response returns a platform prediction row with `id`

## 9. ImageNet Classification Workflow (Annotate + Train + Predict + Review)

- [ ] Run `make seed-imagenet-poc` against a healthy dev stack for a fast 64-sample proof of concept, or `make seed-imagenet-mock` for the offline synthetic dataset
- [ ] Open http://localhost:5173/dashboard and verify `prediction-worker` is healthy before running predictions
- [ ] Open http://localhost:5173/datasets and navigate to the target dataset, then click `Open Workflow`
- [ ] Select dataset `ImageNet-1K Real` for POC/full runs or `ImageNet-1K Mock` for offline runs, then choose the seeded compatible model
- [ ] Click `Run Predictions`
- [ ] Verify the job is accepted instead of returning `API 400: Prediction deployment is not registered`
- [ ] Verify predictions complete and become reviewable
- [ ] Verify the Progress column reflects real sample counts for completed jobs and does not fall back to `0/0` when the job has `sample_ids`
- [ ] Click `Load` for a completed job and verify review rows populate even if the job summary does not embed a `predictions` array
- [ ] Click `Sync Selection to Label Studio` and verify a sync tag is shown in the page
- [ ] In Label Studio, filter predictions by that sync tag inside the same dataset project

Hybrid automation note:
- The current Playwright suite in `apps/web/e2e/` mocks API responses with `page.route(...)`, so it does not validate live seeded data or Prefect deployment availability.
- A practical hybrid smoke test is possible today as a scripted API-level check: seed dev data, submit `POST /api/v1/predictions/run`, then poll `/api/v1/prediction-jobs/{id}` until completion.
- Turning this into a real browser E2E gate requires a separate live-stack Playwright path that does not mock the backend and can authenticate against the seeded stack.

## 9.1 Batch Dev Smoke

- [ ] Run `make seed-imagenet-mock` against a healthy dev stack
- [ ] Run `make smoke-dev-batch`
- [ ] Verify the script finds the seeded ImageNet dataset and model
- [ ] Verify batch prediction completes successfully
- [ ] Verify the bounded prediction smoke completes successfully on the seeded dataset

## 9.2 Training Dev Smoke

- [ ] Run `make smoke-dev-training`
- [ ] Verify the script creates a tiny labeled dataset and starts a real training job
- [ ] Verify the training job reaches `completed`
- [ ] Verify returned training artifacts use shared `s3://` URIs
- [ ] Verify those artifacts exist in the shared MinIO bucket

## 9.2.1 Multi-Image Scatter Demo Seed

- [ ] Run `make seed-multi-image-scatter` against a healthy dev stack
- [ ] Open dataset `Scatter Demo - Multi Image Samples`
- [ ] Verify each sample contains multiple `image_uris`
- [ ] Verify sample metadata includes numeric `scatter_x` and `scatter_y`
- [ ] Verify the interactive scatter component can plot the seeded coordinates and drill into the linked sample viewer

## 9.2.2 Wafer Map Demo (High-Volume Spatial)

This demo tests the virtualization and spatial indexing capabilities with 200k+ points. It is isolated from ImageNet mock flows.

- [ ] Run `make seed-wafer-demo ARGS="--samples 200000 --batch-size 5000 --reset"` against a healthy dev stack.
    - *Note: Rerunning without `--reset` is idempotent.*
- [ ] Open the "Classify" view for the "Wafer Demo" dataset.
- [ ] Verify the **Wafer Map** panel (`data-testid="wafer-map-panel"`) appears in the sidebar.
- [ ] Repeat verification for the **Dataset Detail** view and **Remote Preview** workspace.
- [ ] Drag a region on the wafer map in Classify view to select points.
- [ ] Verify the "Selected Samples" panel updates and displays thumbnails for the selected region.
    - *Note: Previews are bounded by `PREVIEW_HYDRATION_CAP = 50`.*
- [ ] Cmd/Ctrl-click a point to toggle it off and verify linked filtering updates without requiring a replace click.

## 9.3 Prediction Dev Smoke

- [ ] Run `make smoke-dev-prediction`
- [ ] Verify the script creates a tiny labeled dataset and trains a temporary model
- [ ] Verify the real prediction job reaches `completed`
- [ ] Verify prediction summary reports processed and successful samples
- [ ] Verify completed prediction jobs keep a non-empty summary instead of being overwritten with `{}` when Prefect terminal state data is null

## 9.4 Runtime Smoke Bundle

- [ ] Run `make smoke-dev-runtime`
- [ ] Verify both training and prediction smoke checks pass in sequence

## 10. Dashboard

- [ ] Navigate to http://localhost:5173/dashboard
- [ ] Verify statistics load
- [ ] Verify recent items display
- [ ] Verify service health table shows postgres, object storage, prefect, label studio, embedding, training workers, and inference worker

## 10.1 Agent Chat (requires LLM config)

- [ ] Navigate to classify view for a seeded dataset
- [ ] Verify the floating chat FAB button appears in the bottom-right
- [ ] Click the FAB to open the chat drawer
- [ ] Type a message like "Show me annotation stats" and send
- [ ] If LLM is configured: verify SSE events stream (action badges, text reply, sidebar panels)
- [ ] If LLM is NOT configured: verify a 503 error message appears in the chat
- [ ] Verify agent-created panels appear in the sidebar with an "AI" badge
- [ ] Close and reopen the drawer — verify conversation history persists within the session

## 10.2 API Health

```bash
# Health check
curl http://localhost:8000/api/v1/health

# List datasets (requires auth)
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/datasets
```

## 11. Backend Tests

```bash
# Run all API tests
make test

# Run specific test file
make test-api ARGS="tests/test_datasets.py -v"
```

---

## Known Issues

See [`docs/issues/`](./issues/) for tracked issues:
- [Login page styling](./issues/login-page-styling.md) - Input fields have wrong background color

---

## Quick Smoke Test (Minimal)

For a quick verification:

1. `make up` (or `make updev`) - Start stack
2. Open http://localhost:5173/login - Verify page loads
3. Register/login - Verify auth works
4. Create dataset - Verify LS integration
5. Create job - Verify SSE events stream
6. `make test` - Verify backend tests pass
