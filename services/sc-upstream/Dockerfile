FROM python:3.12-slim

WORKDIR /app

COPY libs/protos/ libs/protos/
COPY services/sc-upstream/ services/sc-upstream/

RUN pip install --no-cache-dir -e libs/protos/
RUN pip install --no-cache-dir -e services/sc-upstream/

ENV GRPC_PORT=9091
ENV FLIGHT_PORT=9093
ENV UPSTREAM_DB_URL=sqlite:////data/wafer_inspection.db
ENV ZIPS_DB_URL=sqlite:////data/inspection_zips.db
ENV CACHE_DIR=/data/cache

EXPOSE 9091 9093

CMD ["python", "-m", "sc_upstream.server"]
