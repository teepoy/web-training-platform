# syntax=docker/dockerfile:1
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY apps/embedding/pyproject.toml apps/embedding/pyproject.toml
COPY libs/python-sdk/pyproject.toml libs/python-sdk/pyproject.toml
COPY libs/protos/pyproject.toml libs/protos/pyproject.toml

COPY libs/protos/ libs/protos/
RUN uv sync --frozen --package finetune-embedding --no-install-workspace

COPY apps/embedding/ apps/embedding/
RUN uv sync --frozen --package finetune-embedding

WORKDIR /app/apps/embedding
EXPOSE 50051
CMD ["/app/.venv/bin/python", "-m", "app"]
