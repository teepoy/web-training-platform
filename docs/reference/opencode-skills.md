# OpenCode Skills

Project-local OpenCode skills live under `.opencode/skills/`.

## Available Skills

### `dev-login`

Use this skill when you need to authenticate against the local dev platform API and `curl` authenticated endpoints.

Repo-specific auth details:

- `infra/compose/docker-compose.yaml` exposes Label Studio credentials as `admin@example.com` / `admin123`.
- Those are not the platform API login credentials.
- The platform has no repository-default JWT account. Supply credentials for an
  explicitly registered/provisioned user; local superadmin creation is the
  separate `make create-superadmin EMAIL=... PASSWORD=... NAME=...` operation.
- For org-scoped routes, call `/api/v1/auth/me` after login and pass `X-Organization-ID` on subsequent `curl` requests.
