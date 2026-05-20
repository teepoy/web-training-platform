# Schema-first OpenAPI workflow

`openapi/openapi.yaml` is the single source of truth for transport contracts.

## Generated artifacts

| Artifact | Command | Output |
| --- | --- | --- |
| Backend transport models | `make generate-api-models` | `apps/api/app/generated/openapi_models.py` |
| Frontend transport types | `make generate-web-types` | `apps/web/src/generated/openapi-types.ts` |
| Both | `make generate-openapi-artifacts` | both files |

Backend models are generated with plain `datetime` fields so they stay compatible with the app's existing ORM/domain timestamps.

## Runtime boundaries

- FastAPI serves the canonical schema from `openapi/openapi.yaml`.
- `apps/api/app/api/schemas.py` is now a compatibility surface:
  - generated OpenAPI-backed transport models are re-exported from `app.generated.openapi_models`
  - only non-OpenAPI/internal helper models stay hand-written in `app.api.internal_schemas`
- `apps/web/src/types.ts` is now a compatibility surface:
  - OpenAPI-backed transport types are aliases over `src/generated/openapi-types.ts`
  - UI-only and non-OpenAPI helper types live in `src/ui-types.ts`

## Drift prevention

Run this after route/schema changes:

```bash
make check-openapi-sync
```

It compares the live FastAPI route schema to `openapi/openapi.yaml` and fails if they diverge.

## Editing flow

1. Update `openapi/openapi.yaml`
2. Run `make generate-openapi-artifacts`
3. Update any backend logic or frontend UI-only types that need to adapt
4. Run `make check-openapi-sync`
5. Run the normal test/build commands

## Important constraint

Do not add new hand-written API DTO definitions to `apps/api/app/api/schemas.py` or `apps/web/src/types.ts` when the shape already exists in `openapi/openapi.yaml`. Extend the spec, regenerate, and only keep hand-written types for internal helpers or UI-only models that are intentionally outside OpenAPI.
