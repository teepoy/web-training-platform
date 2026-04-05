## [T9] ScheduleORM
- migration 0009 revision: "abc2def3abc4"
- down_revision: "def3abc4def5" (T4's migration)
- ScheduleORM maps local schedule records to Prefect deployment IDs with org scoping
- fields: id, org_id, created_by, prefect_deployment_id, name, flow_name, cron, parameters, description, is_schedule_active, created_at, updated_at

## [T7] Superadmin CLI
- cli location: apps/api/app/cli.py
- run as: uv run python -m app.cli create-superadmin --email=... --password=... --name=...
- makefile target: create-superadmin with EMAIL= PASSWORD= NAME= vars
- idempotent: promotes existing user or creates new one
## [T5] auth deps.py
- location: apps/api/app/api/deps.py
- get_current_user: Bearer JWT | ?token= query | ftp_ PAT
- get_current_org: X-Organization-ID header, auto-select if 1 org, 400 if ambiguous
- superadmin bypasses org membership check in get_current_org
- zero-org users get 400 (not 403)
- DB access: module-level lazy _session_factory (init on first call via _get_session_factory())
- container.py structure: providers.Singleton for config, db_engine, session_factory; deps.py uses load_config() + create_engine/create_session_factory directly to avoid import cycles
- decode_access_token raises JWTError on invalid token (jose library, re-exported from auth.py)
- verify_personal_access_token(token, token_hash) -> bool uses bcrypt
- PAT: token_prefix = first 8 chars (e.g. "ftp_xxxx"), used for lookup before full hash check
- ORM: UserORM, OrganizationORM, OrgMembershipORM, PersonalAccessTokenORM all in app/db/models.py
- OrgMembership.role: "admin" or "member" (string, not enum)
- User domain model fields: id, email, name, is_superadmin, is_active, created_at
- Organization domain model fields: id, name, slug, created_at
