# Compose Config

`docker-compose.yaml` is now included at `infra/compose/docker-compose.yaml`.

Run:

```bash
docker compose -f infra/compose/docker-compose.yaml up -d
```

From repo root, equivalent Make targets:

```bash
make up
make updev
```

This stack includes:

- postgres
- minio
- api

Notes:

- Compose services run from the image's prebuilt `/app/.venv` and do not use `uv run` at container startup.
- The embedding image installs `torch` during image build, not at container startup.
- The `web` service serves assets baked into the image; it does not bind-mount `apps/web/dist`.
