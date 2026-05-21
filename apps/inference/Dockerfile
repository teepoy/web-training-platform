FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ARG UV_INDEX_URL=""
ARG PIP_INDEX_URL=""

WORKDIR /app

ENV UV_INDEX_URL=${UV_INDEX_URL}
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

COPY pyproject.toml uv.lock ./
COPY apps/inference/pyproject.toml apps/inference/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY libs/protos/pyproject.toml libs/protos/pyproject.toml

COPY libs/protos/ libs/protos/
RUN uv sync --frozen --package finetune-inference --no-install-workspace

COPY apps/inference/ apps/inference/
COPY apps/api/ apps/api/
RUN uv sync --frozen --package finetune-inference

WORKDIR /app/apps/inference
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
