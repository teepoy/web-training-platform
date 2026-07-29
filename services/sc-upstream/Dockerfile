FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.22 /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY libs/protos/pyproject.toml libs/protos/pyproject.toml
COPY services/sc-upstream/pyproject.toml services/sc-upstream/pyproject.toml
COPY libs/protos/ libs/protos/
COPY services/sc-upstream/ services/sc-upstream/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --package sc-upstream --no-dev

ENV GRPC_PORT=9091
ENV FLIGHT_PORT=9093
ENV UPSTREAM_DB_URL=sqlite:////data/wafer_inspection.db
ENV ZIPS_DB_URL=sqlite:////data/inspection_zips.db
ENV CACHE_DIR=/data/cache

EXPOSE 9091 9093

WORKDIR /app/services/sc-upstream
CMD ["/app/.venv/bin/python", "-m", "sc_upstream.server"]
