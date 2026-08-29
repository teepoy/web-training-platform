FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.22 /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY libs/protos/pyproject.toml libs/protos/pyproject.toml
COPY libs/ml/pyproject.toml libs/ml/pyproject.toml
COPY libs/sampling-rules/pyproject.toml libs/sampling-rules/pyproject.toml
COPY libs/klarf/pyproject.toml libs/klarf/pyproject.toml
COPY services/sc-upstream/pyproject.toml services/sc-upstream/pyproject.toml
COPY services/sc-upstream-simulator/pyproject.toml services/sc-upstream-simulator/pyproject.toml
COPY services/sc-upstream-simulator/ services/sc-upstream-simulator/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --package sc-upstream-simulator --no-dev

WORKDIR /app/services/sc-upstream-simulator

EXPOSE 8094

CMD ["/app/.venv/bin/uvicorn", "--factory", "sc_upstream_simulator.server:create_app", "--host", "0.0.0.0", "--port", "8094"]
