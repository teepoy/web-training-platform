# Export Bundle

Use `scripts/export_bundle.sh` to create a portable tar bundle with the repository source snapshot and the Docker images referenced by this repo.

## What it includes

- `source-code.tar.gz` with the current repository snapshot
- `docs/` and `LICENSE` inside that source snapshot
- `docker-images.tar` with locally available Docker images discovered from:
  - `infra/compose/docker-compose.yaml`
  - `infra/k8s/*.yaml`
  - `apps/api/config/base.yaml`
  - `apps/*/Dockerfile`
- image manifest files showing discovered, saved, and missing images

## Usage

```bash
make export-bundle
```

Write to a custom path:

```bash
make export-bundle ARGS="--output /tmp/online-finetune-platform.tar"
```

Pull missing images before saving them:

```bash
make export-bundle ARGS="--pull-missing"
```

## Notes

- Project images such as `finetune-api:latest` must already exist locally unless you build them first.
- If some images are unavailable, the bundle is still created and the missing references are listed in `manifests/images-missing.txt`.
