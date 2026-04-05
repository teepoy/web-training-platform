# syntax=docker/dockerfile:1
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY apps/embedding/pyproject.toml apps/embedding/pyproject.toml
COPY libs/python-sdk/pyproject.toml libs/python-sdk/pyproject.toml
COPY libs/protos/pyproject.toml libs/protos/pyproject.toml

COPY libs/protos/ libs/protos/
RUN uv sync --frozen --package finetune-api --no-install-workspace

COPY apps/api/ apps/api/
COPY apps/worker/ apps/worker/
COPY libs/python-sdk/ libs/python-sdk/
RUN uv sync --frozen --package finetune-api

WORKDIR /app/apps/api
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
