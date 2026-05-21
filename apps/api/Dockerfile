FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ARG UV_INDEX_URL=""
ARG PIP_INDEX_URL=""

WORKDIR /app

ENV UV_INDEX_URL=${UV_INDEX_URL}
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY apps/embedding/pyproject.toml apps/embedding/pyproject.toml
COPY libs/protos/pyproject.toml libs/protos/pyproject.toml

COPY libs/protos/ libs/protos/
RUN uv sync --frozen --package finetune-api --no-install-workspace

COPY apps/api/ apps/api/
COPY libs/seedmaker/ libs/seedmaker/
RUN uv sync --frozen --package finetune-api

WORKDIR /app/apps/api
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
