FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.11.22 /uv /uvx /usr/local/bin/

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
COPY services/sc-upstream/pyproject.toml services/sc-upstream/pyproject.toml

COPY libs/protos/ libs/protos/

FROM base AS deps

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --package finetune-api --no-dev --no-install-workspace

COPY apps/api/ apps/api/
COPY libs/sampling-rules/ libs/sampling-rules/

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
