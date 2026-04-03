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
