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
