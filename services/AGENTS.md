# Services Agent Guide

This directory contains standalone runtime services used by the platform. These are deployable processes wired by `infra/compose` and `infra/k8s`, not the API module service layer.

If this file conflicts with root `AGENTS.md` or `CORE_DESIGNS.md`, treat `CORE_DESIGNS.md` as authoritative and surface the conflict.

## Service Map

| Service      | Path                    | Role                                                                                            |
| ------------ | ----------------------- | ----------------------------------------------------------------------------------------------- |
| SC upstream  | `services/sc-upstream`  | Python gRPC + Arrow Flight service exposing wafer inspection upstream data and zip metadata     |
| SC simulator | `services/sc-upstream-simulator` | Development-only PostgreSQL owner for simulated upstream inspection publication        |
| Image parser | `services/image-parser` | Go HTTP + gRPC service resolving SC image references, sprites, cache, and S3-backed image reads |

Development-only service fixtures belong under the service's `tools/`
directory. Production `src/` packages must not contain or import seed, mock,
dummy, or fake implementations. The root Docker ignore excludes these tools
from release images.

## Boundaries

- Keep these services out-of-process. Do not move FastAPI entrypoints, API route handlers, or API module business services here.
- API code should depend on these services through explicit adapter/protocol boundaries such as SC upstream readers and image fetchers.
- Do not make platform sample identity depend on upstream SC identities. Preserve upstream IDs as provenance only.
- Keep image access aligned with `CORE_DESIGNS.md`: the image-parser service owns all SC image bytes for browser display, prediction, training, and image-bearing exports. API metadata routes may describe image locations but must not proxy or parse SC image bytes.
- Shared wire contracts belong in proto/OpenAPI definitions already used by the repo, not duplicated ad hoc inside a service.
- Service configuration should come from environment/config passed by compose or k8s; do not hardcode deployment URLs.

## Verification

- For `services/sc-upstream`, run service-local Python checks from `services/sc-upstream` when changing Python code. At minimum run targeted tests if they exist and an import/type smoke for touched modules.
- For `services/sc-upstream-simulator`, run its service-local tests and migration
  checks. SQLite is acceptable only for repository unit tests; PostgreSQL
  migration and transaction behavior requires the development database or CI.
- For `services/image-parser`, run Go checks from `services/image-parser`: `go test ./...` for code changes, and `go test ./... -run TestName` for a narrow test while iterating.
- For Docker-relevant service changes, verify the relevant compose image build when feasible, for example `docker compose -f infra/compose/docker-compose.yaml build sc-upstream image-parser`.
- If a required service check cannot be run, state why and what remains unverified.
