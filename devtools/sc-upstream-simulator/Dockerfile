FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.22 /uv /uvx /usr/local/bin/

WORKDIR /workspace/devtools/sc-upstream-simulator

COPY libs/protos /workspace/libs/protos
COPY services/sc-upstream /workspace/services/sc-upstream
COPY devtools/sc-upstream-simulator /workspace/devtools/sc-upstream-simulator

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8094 9091 9093

CMD ["/workspace/devtools/sc-upstream-simulator/.venv/bin/uvicorn", "--factory", "sc_upstream_simulator.server:create_app", "--host", "0.0.0.0", "--port", "8094"]
