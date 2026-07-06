#!/bin/sh
set -eu

process_index="${1:?Perspective process index is required}"
port=$((8001 + process_index))

exec /app/.venv/bin/uvicorn app.perspective_main:app \
  --host 0.0.0.0 \
  --port "${port}" \
  --timeout-keep-alive "${UVICORN_TIMEOUT_KEEP_ALIVE:-120}" \
  --timeout-graceful-shutdown "${UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN:-600}" \
  --timeout-worker-healthcheck "${UVICORN_TIMEOUT_WORKER_HEALTHCHECK:-60}"
