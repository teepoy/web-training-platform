# Configuration Ownership

The API has three configuration owners. A value must belong to exactly one of
them:

1. Tracked profile YAML owns stable application behavior and limits.
2. Environment variables own secrets and deployment topology.
3. Module registries/descriptors own executable categories and routing metadata.

`APP_CONFIG_PROFILE` selects `base.yaml` plus one tracked profile override:
`dev.yaml`, `pre-release.yaml`, `prod.yaml`, or `test.yaml`. Production images
bundle these files. Operators do not generate or mount a replacement
`prod.yaml`. Unknown/retired YAML fields are ignored for compatibility, but are
not exposed through the typed configuration model.

## Environment-owned inputs

There are no aliases for these names. Values supplied through an environment
variable replace the empty deployment slot from tracked YAML; no second
environment name or command-line flag is supported.

| Owner                | Canonical inputs                                                                                             | Type and default policy                                                                          |
| -------------------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| Profile selection    | `APP_CONFIG_PROFILE`                                                                                         | Enum; defaults to `dev` for host development. Deployments set it explicitly.                     |
| Browser/API topology | `FRONTEND_URL`                                                                                               | URL; required outside tests.                                                                     |
| Platform database    | `DATABASE_URL`                                                                                               | Secret-bearing PostgreSQL URL; required for deployable profiles.                                 |
| Artifact storage     | `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`                                                     | Endpoint plus credentials; required for deployable profiles.                                     |
| Label Studio         | `LABEL_STUDIO_URL`, `LABEL_STUDIO_EXTERNAL_URL`, `LABEL_STUDIO_API_KEY`, `LABEL_STUDIO_DATABASE_URL`         | Internal/public URLs and secret-bearing credentials; required for deployable profiles.           |
| Prefect              | `PREFECT_API_URL`, `PREFECT_UI_URL`                                                                          | Internal API and public UI URLs; required for deployable profiles.                               |
| Redis                | `REDIS_HOST`, `REDIS_PASSWORD`                                                                               | Host is required outside tests; empty password is supported. Port/database remain profile-owned. |
| LLM                  | `LLM_BASE_URL`, `LLM_API_KEY`                                                                                | Optional endpoint and secret. Empty values disable LLM-backed features.                          |
| Authentication       | `JWT_SECRET_KEY`                                                                                             | Required secret outside tests; insecure placeholders fail startup.                               |
| OAuth                | `OAUTH_STATE_SECRET`, `OAUTH_{GOOGLE,GITHUB,CUSTOM}_CLIENT_ID`, `OAUTH_{GOOGLE,GITHUB,CUSTOM}_CLIENT_SECRET` | Required only for enabled providers. Provider URLs/scopes remain YAML-owned.                     |
| SC upstream          | `SC_UPSTREAM_ADDR`, `SC_UPSTREAM_FLIGHT_ADDR`, `IMAGE_PARSER_GRPC_ADDR`                                      | Required service addresses for deployable profiles.                                              |
| SC cache placement   | `SC_DATA_PROVIDER_CACHE_DIR`, `SC_DATA_PROVIDER_CACHE_NAMESPACE`                                             | Required mounted path and pod/process namespace for deployable profiles.                         |

Database and migration CLIs consume the same `DATABASE_URL` and profile loader.
Development Make targets only assemble these canonical environment inputs for
host processes; they do not define a second application setting.

## Tracked YAML-owned inputs

The default column below means the value in tracked `base.yaml`; profile files
may override it for the named environment. Environment variables with similar
or historical names are ignored.

| Section                 | Canonical paths                                                                                                                                                                                                                     | Owner/type/default policy                                                                                             |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Application             | `app.env`                                                                                                                                                                                                                           | Profile identity; each profile file must match its selected name.                                                     |
| Execution               | `execution.engine`, `execution.status_reconcile_interval_seconds`                                                                                                                                                                   | Engine enum and positive interval; test uses local, deployable profiles use Prefect.                                  |
| Logging                 | `logging.level`                                                                                                                                                                                                                     | Process log threshold; `INFO` in development and `WARNING` in test/deployable profiles.                               |
| Database behavior       | `db.echo`, `db.auto_create`                                                                                                                                                                                                         | Booleans; false outside the test profile.                                                                             |
| Storage behavior        | `storage.kind`, `storage.runtime_bucket`, `storage.sparse_manifest_cache_max_bytes`, `storage.minio.bucket`, `storage.minio.secure`, `storage.minio.lifecycle.exports.*`                                                            | Adapter choice, bucket identities, cache limit, and lifecycle policy. Test-only memory storage is rejected elsewhere. |
| Kubernetes/Kubeflow     | `k8s.namespace`, `k8s.incluster`, `k8s.kubeconfig`, `kubeflow.group`, `kubeflow.version`, `kubeflow.plural`, `kubeflow.image`                                                                                                       | Training-operator client and resource contract. Profile overrides select cluster access.                              |
| Notifications           | `notification.webhook.endpoint`, `notification.webhook.timeout_seconds`                                                                                                                                                             | Webhook integration behavior and timeout. No separate sink selector exists.                                           |
| OAuth behavior          | `oauth.enabled`, provider `display_name`, `enabled`, endpoint URLs, scopes, and `user_mapping`                                                                                                                                      | Provider catalog configuration; secrets remain environment-owned.                                                     |
| LLM behavior            | `llm.model`, `llm.timeout_seconds`                                                                                                                                                                                                  | Provider-routed model ID and request timeout.                                                                         |
| Agent                   | `agent.enabled`, `agent.metadata_sample_size`                                                                                                                                                                                       | Feature switch and bounded context sample size.                                                                       |
| Prediction compaction   | `prediction.compaction_memory_limit`, `prediction.compaction_temp_limit`, `prediction.compaction_row_group_rows`                                                                                                                    | Compaction resource bounds.                                                                                           |
| Dataset transfers       | `dataset_transfer.annotation_import_max_bytes`, `dataset_transfer.annotation_import_max_records`, `dataset_transfer.annotation_batch_rows`, `dataset_transfer.parquet_import_max_bytes`, `dataset_transfer.parquet_import_max_rows` | Import byte/record ceilings and persistence batch sizes for annotation and Parquet transfers.                         |
| Redis behavior          | `redis.port`, `redis.db`                                                                                                                                                                                                            | Port/database number; host/password are deployment-owned.                                                             |
| Startup                 | `startup_checks.dependency_timeout_seconds`                                                                                                                                                                                         | Positive dependency-check timeout.                                                                                    |
| Authentication behavior | `auth.enabled`, `auth.jwt_algorithm`, `auth.access_token_expire_minutes`                                                                                                                                                            | Authentication cannot be disabled; algorithm and token lifetime are stable policy.                                    |
| SC pipeline             | every `sc.pipeline.*` field                                                                                                                                                                                                         | Import, materialization, prediction, progress, and training bounds.                                                   |
| SC data provider        | `sc.data_provider.*` except cache directory/namespace                                                                                                                                                                               | DuckDB implementation, memory/thread/resource budgets, cache policy, leases, timeouts, batch sizes, and SSE limits.   |

## Registry-owned inputs

Prefect deployment names, flow entrypoints, work pools, work queues, priorities,
and deployment-owned schedules live in the repository deployment catalog. The
Dashboard consumes the same catalog and does not carry a YAML copy of a pool
name. Dataset types, widgets, import/export flows, runtime capabilities, source
providers, and similar executable categories remain in their module-owned
registries/descriptors.

## Failure and compatibility behavior

- Missing required deployable inputs fail startup with the typed config path.
- Deployable profiles reject SQLite, in-memory storage, and local execution.
- Retired environment-variable names have no aliases and no precedence.
- Retired extra YAML fields are ignored during compatibility reads and omitted
  from the typed model; they cannot affect behavior.
- Stable limits do not gain command-line or environment overrides. A change is
  made in tracked YAML and reviewed as application configuration.
