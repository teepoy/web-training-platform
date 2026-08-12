# Schedule Execution

The Schedule module is the product-facing owner of recurring jobs. The API
database is the source of truth for ownership, display name, cron, timezone,
parameters, and lifecycle state. Prefect owns deployment execution and run
state.

## Executable targets

Users cannot schedule arbitrary Prefect flow names. The API exposes
`GET /api/v1/schedules/capabilities`, backed by the repository-owned
`PrefectDeploymentSpec` objects in
`app/shared/infrastructure/prefect/deployments.py`. A spec is available to the
Schedule module only when it is explicitly included in the schedulable set.
The initial supported target is `drain-dataset` on `default-cpu`.

Adding a target requires an implemented flow plus its declared entrypoint,
path, work pool, and an explicit schedulable registration. The frontend reads
the capability endpoint; it does not keep its own list of flow names.

## Creation and identity

Each product schedule gets a unique local UUID and a dedicated Prefect
deployment named `platform-schedule-{schedule_id}`. The deployment is created
from the registered spec with its work pool, entrypoint, path, parameters, and
these tags:

- `platform-schedule`
- `platform-org:{org_id}`
- `platform-schedule-id:{schedule_id}`

The user-facing schedule name is metadata and can change without renaming the
internal Prefect deployment. This avoids Prefect name collisions between
organizations.

Creation writes Prefect first and compensates by deleting the deployment if
the database write fails. Updates write Prefect first and restore the previous
Prefect values if the database update fails. These compensations are
best-effort because the database and Prefect do not share a transaction;
operators should investigate the structured error log if compensation itself
fails. Deletion treats an already-missing Prefect deployment as success, so a
request can be retried safely if the remote deletion succeeded before a local
database failure.

## Time and access rules

The public contract uses five-field cron expressions in the order `minute hour
day month weekday`. Every schedule stores an explicit IANA timezone; `UTC` is
the compatibility default for clients that omit it.

Schedule rows, runs, and run logs are organization-scoped. A run or log lookup
first proves that its Prefect deployment belongs to a schedule in the current
organization. The frontend uses the Prefect UI deep link returned by the API,
which is derived from the configured `PREFECT_UI_URL`.
