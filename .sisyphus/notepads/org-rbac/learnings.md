# Org RBAC Learnings

## T18 — Org-scoped queries + auth guard + 0-org state (2026-04-06)

### Changes made
- All 6 list views (`DatasetsView`, `JobsView`, `PresetEditorView`, `SchedulesView`, `PredictionsView`, `DashboardView`) updated:
  - `useOrgStore` imported from `../stores/org`
  - `useQuery` queryKeys updated to `computed(() => [key, orgStore.currentOrgId])`
  - `enabled: computed(() => !!orgStore.currentOrgId)` added to all queries
  - `invalidateQueries` calls updated to include `orgStore.currentOrgId`
  - 0-org state added with `<n-empty>` and message "You are not a member of any organization. Contact an admin."

- `api.ts` hardcoded "web-user" removed:
  - `createAnnotation`: `created_by` only sent if `body.created_by` is provided (no fallback)
  - `createJob`: `created_by` field removed entirely from POST body
  - `editPrediction`: `edited_by` fallback `?? "web-user"` removed (bonus cleanup)

### Auth guard
- `router.ts` already has a `beforeEach` guard using `localStorage.getItem('auth_token')`
- Redirects to `/login` for unauthenticated access — no changes needed

### Pattern for computed queryKeys in Vue Query
```typescript
useQuery({
  queryKey: computed(() => ['key', orgStore.currentOrgId]),
  queryFn: api.listSomething,
  enabled: computed(() => !!orgStore.currentOrgId),
})
```

### Build
- `make build-web` passes with exit 0
- Only informational warnings (chunk size, dynamic import collocation) — not errors

## T19 — Seed default superadmin migration (2026-04-06)

### Changes made
- Added Alembic migration `0011_seed_default_org_and_superadmin.py` chained from `bcd4ef5bcd6a`.
- Seeded `users` with the default superadmin and `org_memberships` linking them to the default org.
- Downgrade removes only the membership and user; default org remains intact.

### Migration pattern
- Direct `op.execute(sa.text(...))` inserts were used with literal values.
- Seed inserts are guarded with `try/except IntegrityError` so reruns stay idempotent.

## T20 — Public flags on dataset/job models (2026-04-06)

### Changes made
- Added `is_public: bool = False` to `Dataset` and `TrainingJob` domain models.
- Added `is_public` Boolean columns to `DatasetORM` and `TrainingJobORM` with `default=False`, `nullable=False`, and `server_default="0"`.
- Created Alembic migration `0012_add_is_public_flag.py` using `op.batch_alter_table()` for both tables to stay SQLite-compatible.

### Migration pattern
- Use `batch_alter_table()` for NOT NULL column additions on SQLite.
- Keep ORM/domain defaults aligned so new objects stay private by default.

## T24 — PAT token + org header SDK/CLI support (2026-04-06)

### Changes made
- `FinetuneClient` now accepts `org_id` alongside `token` and adds `X-Organization-ID` when present.
- `start_training()` no longer sends `created_by`; agent wrappers mirror the same signature.
- CLI global callback stores `--token` / `--org-id` with `FTCTL_TOKEN` / `FTCTL_ORG_ID` fallbacks.
- `jobs watch` appends `?token=...` for SSE auth.

### Pattern
- Typer global options via `@app.callback()` are the simplest way to share auth state across subcommands.
- Browser/EventSource SSE still needs query-token fallback because headers are unavailable.

## T22: user_id FK columns alongside created_by (migration 0013)

- ORM pattern for nullable FK: `user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)` — added after the last existing column in each class
- Migration 0013 uses `op.batch_alter_table()` without FK constraint spec (SQLite batch mode doesn't enforce FKs anyway); the ORM model carries the relationship definition
- Repository `create_*` methods accept `user_id: str | None = None` as optional kwarg; existing callers need no changes since default is None
- Tables: `training_jobs`, `annotations`, `prediction_edits` (verified by reading `__tablename__`)
- 173 tests pass with no changes to test files
- `created_by`/`edited_by` string fields remain unchanged — user_id is strictly additive

## T21: Public Resource Visibility + PATCH Toggle + Org Context

### Patterns used
- `or_(ORM.org_id == org_id, ORM.is_public == True)` — SQLAlchemy filter for "mine or public"
- `or_` must be explicitly imported: `from sqlalchemy import func, or_, select, text`
- For `get_*` methods: check `if org_id is not None and row.org_id != org_id and not row.is_public`
- `require_superadmin` is called directly as `await require_superadmin(current_user=current_user)`, not as a FastAPI Depends
- New repository methods `set_dataset_public` and `set_job_public` keep ORM mutation in the repo layer
- `ModelAssetVersion` and `ModelAssetSummary` added as new schemas in schemas.py (weren't in codebase before)
- `SetPublicRequest` schema with `is_public: bool` for PATCH body

### Test result
- 194 passed, 4 skipped after changes (was 194+/173+ previously). All clean.

### LSP errors
- `Import "sqlalchemy" could not be resolved` — expected, sqlalchemy not stubbed in this env. Not a runtime issue.
