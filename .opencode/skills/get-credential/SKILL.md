---
name: get-credential
description: Look up the correct dev credentials and authenticate against the local platform API, seed scripts, Label Studio, and other local services.
compatibility: opencode
metadata:
  audience: contributors
  workflow: credential-lookup
---

## What I do

- Return the correct credentials for a given local dev context (platform admin, seed scripts, Label Studio, MinIO, pgAdmin).
- Prevent accidental cross-use of credentials between services.
- Authenticate against the local platform API and attach JWT + org headers to requests.

## Credential Table

| Context | Email | Password | Name | Source |
|---------|-------|----------|------|--------|
| Platform dev admin | `admin@localhost` | `admin` | Admin | `apps/api/alembic/versions/0011_seed_default_org_and_superadmin.py`, `scripts/dev-init.sh` |
| Seed scripts | `seed@example.com` | `seed1234` | Seed Admin | `scripts/seed_imagenet_dev.py`, `scripts/seed_imagenet_real.py`, `scripts/seed_oxford_flowers.py`, `scripts/seed_presets.py` |
| Label Studio | `admin@example.com` | `admin123` | — | `infra/compose/docker-compose.yaml` (`LABEL_STUDIO_USERNAME` / `LABEL_STUDIO_PASSWORD`) |
| pgAdmin | `admin@example.com` | `admin123` | — | `infra/compose/docker-compose.yaml` |
| MinIO | `minioadmin` | `minioadmin` | — | `infra/compose/docker-compose.yaml` |

## When To Use Each

- **Platform admin** (`admin@localhost` / `admin`): Interactive API testing, `curl` against `http://localhost:8000/api/v1/auth/login`. Use for smoke-testing authenticated endpoints.
- **Seed scripts** (`seed@example.com` / `seed1234`): All `make seed-*` targets. The seed scripts register this user, optionally promote to superadmin, then login. Use these credentials when writing or debugging seed scripts.
- **Label Studio** (`admin@example.com` / `admin123`): Accessing Label Studio UI or API directly. Do NOT use these for platform JWT login.
- **MinIO** (`minioadmin` / `minioadmin`): S3-compatible storage console at `http://localhost:9001`.

## Login Workflow

Use this workflow when you need to call authenticated platform API endpoints with `curl`.

1. Verify the API is reachable:

```bash
curl -sf http://localhost:8000/health
```

2. Pick the correct credentials from the table above, then obtain a JWT:

```bash
TOKEN=$(curl -sf -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@localhost","password":"admin"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
```

3. Use the token on API requests:

```bash
curl -sf http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

4. If the route is org-scoped, get the first org id and send it too:

```bash
ORG_ID=$(curl -sf http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data["organizations"][0]["org_id"] if data["organizations"] else "")')

curl -sf http://localhost:8000/api/v1/datasets \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-ID: $ORG_ID"
```

## Repo-Specific Rules

- `infra/compose/docker-compose.yaml` contains `LABEL_STUDIO_USERNAME` and `LABEL_STUDIO_PASSWORD` for Label Studio only. Do not use those credentials for platform JWT login.
- The platform dev superadmin is the migration-seeded account in `apps/api/alembic/versions/0011_seed_default_org_and_superadmin.py` and is also documented in `scripts/dev-init.sh`.
- Seed scripts define their own constants (`SEED_EMAIL`, `SEED_PASSWORD`, `SEED_NAME`) at the top of each file. All four scripts currently use the same values.
- The platform dev admin is migration-seeded via Alembic and is separate from the seed-script user.
- Health checks use `/health`; versioned API routes use `/api/v1/...`.
- These are dev/smoke-test secrets. Never reuse them in production.

## Failure Handling

- If login with platform admin fails with `401`, verify the local stack is running and migrations ran (`make db-migrate`).
- If login with seed credentials fails, verify the seed user was registered first (`POST /api/v1/auth/register`).
- If `/api/v1/auth/me` returns no organizations, ask the user whether they want to create one or use a different account.
- If the user explicitly wants Label Studio pages instead of platform API routes, use the Label Studio credentials from compose and do not request a platform JWT.
- If the user reports different credentials, trust them and update the skill accordingly.
