# syntax=docker/dockerfile:1
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/inference/pyproject.toml apps/inference/pyproject.toml
RUN uv sync --frozen --package finetune-inference --no-install-workspace

COPY apps/inference/ apps/inference/
RUN uv sync --frozen --package finetune-inference

WORKDIR /app/apps/inference
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
