# Compose Config

`docker-compose.yaml` is now included at `infra/compose/docker-compose.yaml`.

Run:

```bash
docker compose -f infra/compose/docker-compose.yaml up -d
```

This stack includes:

- postgres
- minio
- api

Notes:

- Compose services run from the image's prebuilt `/app/.venv` and do not use `uv run` at container startup.
- The embedding image installs `torch` during image build, not at container startup.
