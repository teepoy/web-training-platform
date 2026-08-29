FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.22 /uv /uvx /usr/local/bin/

WORKDIR /app

COPY devtools/sc-upstream-simulator/pyproject.toml devtools/sc-upstream-simulator/uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY devtools/sc-upstream-simulator/ ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8094

CMD ["/app/.venv/bin/uvicorn", "--factory", "sc_upstream_simulator.server:create_app", "--host", "0.0.0.0", "--port", "8094"]
