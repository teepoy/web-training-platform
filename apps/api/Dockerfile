FROM golang:1.26-bookworm AS image-parser-batch-builder

WORKDIR /src
COPY services/image-parser/go.mod services/image-parser/go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY services/image-parser/ ./
RUN --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /image-parser-batch ./cmd/batch-resolve

FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.11.22 /uv /uvx /usr/local/bin/
COPY --from=image-parser-batch-builder /image-parser-batch /usr/local/bin/image-parser-batch

ARG UV_INDEX_URL=""
ARG PIP_INDEX_URL=""

WORKDIR /app

ENV UV_INDEX_URL=${UV_INDEX_URL}
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY libs/protos/pyproject.toml libs/protos/pyproject.toml
COPY libs/ml/pyproject.toml libs/ml/pyproject.toml
COPY libs/sampling-rules/pyproject.toml libs/sampling-rules/pyproject.toml
COPY libs/klarf/pyproject.toml libs/klarf/pyproject.toml
COPY services/sc-upstream/pyproject.toml services/sc-upstream/pyproject.toml

COPY libs/protos/ libs/protos/

FROM base AS deps

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --package finetune-api --no-dev --no-install-workspace

COPY apps/api/ apps/api/
COPY libs/sampling-rules/ libs/sampling-rules/
COPY libs/klarf/ libs/klarf/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --package finetune-api --no-dev

FROM deps AS dev

WORKDIR /app/apps/api
EXPOSE 8000
CMD ["fastapi", "dev", "app/main.py", "--host", "0.0.0.0", "--port", "8000", "--reload-dir", "/app/apps/api"]

FROM deps AS prod

WORKDIR /app/apps/api
EXPOSE 8000
ENV UVICORN_TIMEOUT_KEEP_ALIVE=120
ENV UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=600
ENV UVICORN_TIMEOUT_WORKER_HEALTHCHECK=60
CMD ["sh", "-lc", "exec /app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --timeout-keep-alive ${UVICORN_TIMEOUT_KEEP_ALIVE:-120} --timeout-graceful-shutdown ${UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN:-600} --timeout-worker-healthcheck ${UVICORN_TIMEOUT_WORKER_HEALTHCHECK:-60}"]
