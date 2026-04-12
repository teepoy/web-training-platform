---
name: dev-login
description: Authenticate against the local dev platform API, derive the correct dev admin account, and attach JWT headers to curl requests.
compatibility: opencode
metadata:
  audience: contributors
  workflow: local-dev-auth
---

## What I do

- Authenticate against the local platform API running on `http://localhost:8000`.
- Check `infra/compose/docker-compose.yaml` first to confirm local service wiring and the Label Studio admin username.
- Use the platform dev superadmin account to obtain a JWT from `POST /api/v1/auth/login`.
- Include `Authorization: Bearer <token>` on `curl` requests to `http://localhost:8000/api/v1/...`.
- For org-scoped API routes, fetch `/api/v1/auth/me` and include `X-Organization-ID: <org_id>`.

## Repo-Specific Rules

- `infra/compose/docker-compose.yaml` contains `LABEL_STUDIO_USERNAME` and `LABEL_STUDIO_PASSWORD` for Label Studio only. Do not use those credentials for platform JWT login.
- The platform dev superadmin is the migration-seeded account in `apps/api/alembic/versions/0011_seed_default_org_and_superadmin.py` and is also documented in `scripts/dev-init.sh`.
- In this repo, the platform login credentials are `admin@localhost` / `admin` unless the user says their local environment differs.
- Health checks use `/health`; versioned API routes use `/api/v1/...`.

## Default Workflow

1. Read `infra/compose/docker-compose.yaml` to confirm the dev stack is the local compose environment.
2. Read `apps/api/alembic/versions/0011_seed_default_org_and_superadmin.py` or `scripts/dev-init.sh` to resolve the platform admin account.
3. Verify the API is reachable with `curl -sf http://localhost:8000/health`.
4. Log in to the platform API:

```bash
TOKEN=$(curl -sf -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@localhost","password":"admin"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
```

5. Use the token on API requests:

```bash
curl -sf http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

6. If the route is org-scoped, get the first org id and send it too:

```bash
ORG_ID=$(curl -sf http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data["organizations"][0]["org_id"] if data["organizations"] else "")')

curl -sf http://localhost:8000/api/v1/datasets \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-ID: $ORG_ID"
```

## When To Use Me

Use this skill whenever you need to inspect or smoke-test authenticated API endpoints in the local dev environment with `curl`.

## Failure Handling

- If login fails with `401`, verify the local stack is running and the seeded superadmin still uses `admin@localhost` / `admin`.
- If `/api/v1/auth/me` returns no organizations, ask the user whether they want to create one or use a different account.
- If the user explicitly wants Label Studio pages instead of platform API routes, use the Label Studio credentials from compose and do not request a platform JWT.
