#!/bin/sh
set -eu

process_index="${1:?Perspective process index is required}"
port=$((8001 + process_index))

export MALLOC_CONF="${PERSPECTIVE_WS_MALLOC_CONF:-background_thread:true,dirty_decay_ms:1000,muzzy_decay_ms:1000,retain:false}"

exec /app/.venv/bin/uvicorn app.perspective_main:app \
  --host 0.0.0.0 \
  --port "${port}" \
  --timeout-keep-alive "${UVICORN_TIMEOUT_KEEP_ALIVE:-120}" \
  --timeout-graceful-shutdown "${UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN:-600}" \
  --timeout-worker-healthcheck "${UVICORN_TIMEOUT_WORKER_HEALTHCHECK:-60}"
