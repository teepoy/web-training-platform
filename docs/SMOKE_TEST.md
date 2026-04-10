# Smoke Test Checklist

Run this checklist after making significant changes to verify core functionality.

## Prerequisites

```bash
# Start the full stack
make up

# Wait for all services to be healthy
docker compose -f infra/compose/docker-compose.yaml ps
```

Services should be running:
- `compose-api-1` - API server (port 8000) — also runs the embedded Prefect flow runner
- `compose-web-1` - Web frontend (port 5173)
- `compose-postgres-1` - PostgreSQL (port 5432)
- `compose-minio-1` - MinIO storage (ports 9000, 9001)
- `compose-prefect-server-1` - Prefect server (port 4200)
- `compose-label-studio-1` - Label Studio (port 8080)
- `compose-training-worker-1` - Training worker (GPU, V2 mode)
- `compose-embedding-1` - Embedding service (port 50051)

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

## 4. Training Presets

### 4.1 List Presets
- [ ] Navigate to http://localhost:5173/presets
- [ ] Verify default presets are listed (yolov8n-cls, resnet18, etc.)

### 4.2 Create Preset
- [ ] Click "New Preset"
- [ ] Fill in preset details
- [ ] Verify preset appears in list

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
- [ ] Verify training chart updates

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

## 8. Dashboard

- [ ] Navigate to http://localhost:5173/dashboard
- [ ] Verify statistics load
- [ ] Verify recent items display

## 9. API Health

```bash
# Health check
curl http://localhost:8000/api/v1/health

# List datasets (requires auth)
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/datasets
```

## 10. Backend Tests

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

1. `make up` - Start stack
2. Open http://localhost:5173/login - Verify page loads
3. Register/login - Verify auth works
4. Create dataset - Verify LS integration
5. Create job - Verify SSE events stream
6. `make test` - Verify backend tests pass
