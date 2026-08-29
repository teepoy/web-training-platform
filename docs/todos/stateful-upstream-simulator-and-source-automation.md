# TODO: Build a Stateful Upstream Simulator for Source Automation

## Progress

- **Overall status:** In progress; the database, control, platform-facing read
  interfaces, and simulator-owned showcase publication are complete. Recurring
  Collection discovery remains.
- **Completed intermediate slices:** resolved the PostgreSQL, HTTP API, CLI,
  latest-value, and five-minute automation decisions; recorded the current
  direct-write inventory; moved the artifact generator out of Compose code;
  established a root `devtools/` boundary and moved the separate
  `devtools/sc-upstream-simulator` package beneath it with its initial
  Alembic migration, and transactional draft-to-published state with a monotonic
  change token; added the bearer-authenticated HTTP control API, HTTP-only CLI,
  simulator-owned development database, and Compose service; and separated its
  dependency lock and image build from the production uv workspace/images.
  The simulator now also serves published rows through the existing gRPC and
  Arrow Flight contracts, transports latest-update/change-token freshness, and
  performs metadata reads directly so mutable source values are never hidden by
  the production query cache. A named, idempotent HTTP scenario now generates
  deterministic defects, review images, patch archives, PostgreSQL metadata,
  and object-store payloads inside the simulator and publishes them coherently;
  the CLI and platform seed recipe use that same API.
- **Next milestone:** add the five-minute internal Collection-discovery trigger.
- **Done when:** every acceptance criterion below is verified. Package
  relocation is not simulator completion.

This document records the proposal to replace distributed SC fixture scripts
with a stateful development upstream service and database that can simulate
source behavior over time. It is an audit and architecture proposal only. No
service, database, seed, sensor, or automation behavior should be changed until
the target boundary and migration order are approved.

This todo refines the SC portions of
`docs/todos/mock-seed-code-package-separation.md`. The earlier todo correctly
identifies that mock database implementations do not belong in the production
service package. The intended replacement here is not another moved seed
script: it is a development-only upstream simulator with an owned database and
an explicit behavior/control interface.

## Resolved Decisions

- The simulator is a separately named development-only package/service backed
  by its own PostgreSQL database.
- It exposes an HTTP control API and a thin CLI client. Upstream scenario
  behavior is not implemented as Make targets or direct database/object-store
  scripts.
- Repository development seeding calls the simulator API for every upstream
  record. Platform-owned seed data remains in `devtools/seedmaker/`.
- The initial simulator supports creating and publishing inspections and
  updating mutable fields on published rows. Deletion/tombstones, outages,
  artificial latency, delayed assets, and incomplete publication are deferred.
- Active Collection membership rules are the product surface for upstream
  discovery. Retain internal sensor scheduling capability, remove the legacy
  timer/dataset-size definitions and generic Sensor subscription UI/API, and
  add an internal Collection-discovery sensor whose definition owns the
  five-minute interval.
- If a run for the same Collection rule is still active at the next tick, skip
  the new run and record that outcome; do not queue duplicate runs.
- Discovery and imported Datasets use current-state semantics. Mutable upstream
  field changes become visible dynamically and do not create a historical
  source revision, re-import requirement, or Needs attention state.
- Except for deployment/configuration cleanup, existing product behavior and
  stored-data reads remain backward-compatible. No data backfill is required.

## Current Findings

### The current `sc-upstream` is a real process over a mock database adapter

The development stack already starts a separate gRPC and Arrow Flight service,
and the API reads it through `GrpcScUpstream`. However, the normal service
entrypoint always constructs classes named `_MockUpstreamDB` and
`_MockInspectionZipsDB`. The release service uses the same entrypoint.

Relevant files:

- `services/sc-upstream/src/sc_upstream/server.py`
- `services/sc-upstream/src/sc_upstream/upstream_db.py`
- `services/sc-upstream/src/sc_upstream/models.py`
- `services/sc-upstream/src/sc_upstream/service.py`
- `services/sc-upstream/src/sc_upstream/flight_server.py`
- `services/sc-upstream/src/sc_upstream/cache.py`
- `services/sc-upstream/Dockerfile`
- `protos/sc/v1/upstream.proto`
- `apps/api/app/modules/sc/adapter/grpc_upstream.py`
- `apps/api/app/modules/sc/container.py`
- `infra/compose/docker-compose.dev.yaml`
- `infra/compose/production/compose.platform.yaml`

The current implementation is SQLite-oriented and the service package only
declares the SQLite async driver. Supplying a production `UPSTREAM_DB_URL` does
not by itself provide a verified production database adapter. A development
simulator and a real production adapter are separate deliverables and must not
be represented as the same thing.

### Upstream fixture state is written by several independent scripts

Files and entrypoints:

- `devtools/seedmaker/legacy_sc_sqlite.py`
  - Writes inspection summaries, defects, recipes, classes, and review-image
    metadata directly into SQLite.
  - Provides mass and gallery scenarios.
  - Advertises a `representative` subcommand, but the current command dispatch
    does not populate representative inspections.
- `devtools/seedmaker/sc_artifacts.py` (moved from Compose infrastructure)
  - Reads the inspection SQLite database, generates image archives, uploads
    objects to MinIO, writes a second SQLite zip-metadata database, and directly
    clears the upstream disk cache.
- The removed `infra/compose/seed_review_images.py` was another image-fixture
  path with no caller and overlapped the newer patch-zip workflow.
- `make/build.mk`
  - Coordinates multiple fixture commands, repeats paths and counts, clears or
    restarts services, and contains separate mass/gallery variants.
- `Makefile`
  - Owns another set of fixture counts, timestamps, bucket names, and endpoints.
- `devtools/seedmaker/datasets/dev_showcase.py`
  - Assumes the upstream fixture already exists, imports its latest inspection,
    creates platform collections and a source connector, creates a manual-only
    membership rule, then creates disabled legacy sensor subscriptions.
- `devtools/seedmaker/dev_activity.py`
  - Inserts non-executing platform jobs, models, metrics, and events directly for
    display purposes; this is platform fixture data, not upstream behavior.

The result is snapshot seeding rather than behavioral simulation. Creating a
new inspection requires coordinated database writes, object-store writes,
cache clearing, service restarts, and platform seed calls. It cannot naturally
model “an upstream record arrives after the automation watermark” or “an
existing source record changes after import.”

### The legacy sensor subsystem does not observe SC upstream records

Files:

- `apps/api/app/modules/jobs/sensors/`
- `apps/api/sensors/dataset_size_sensor.yaml`
- `apps/api/sensors/timer_sensor.yaml`
- `apps/api/app/shared/infrastructure/prefect/deployments.py`
- `apps/web/src/features/sensors/router.ts`
- `apps/web/src/features/sensors/presentation/pages/SensorsView.vue`
- `apps/web/src/features/sensors/presentation/pages/SensorSubscriptionModal.vue`
- `docs/architecture/sensor-pubsub.md`

The registered sensor flows are a timer and a platform dataset-size poller.
Neither reads `sc-upstream`. The web sensor route exists in its feature package
but is not registered by the application router. This aligns with the current
`CORE_DESIGNS.md` decision that Schedule/Sensor/Subscription are internal
implementation terms and that the old global sensor UI should not remain the
product model.

There is also a mismatch inside the legacy fixture itself:

- `dataset_size_sensor.py` emits `sample_count`.
- `dataset_size_sensor.yaml` describes `min_sample_count` as a threshold.
- `SensorDispatchService._matches_filter()` performs only exact key/value
  equality, so a `min_sample_count` subscription cannot match those events.
- `dev_showcase.py` creates this kind of subscription, but leaves it disabled.

This subsystem should be explicitly retired, reduced to an internal trigger
adapter, or reconciled with the resource-automation design before new upstream
behavior is connected. The simulator must not accidentally make this legacy
generic subscription model the new product architecture.

### Current source discovery already uses the upstream service, but only on demand

Files:

- `apps/api/app/modules/source_discovery/adapter/sc_provider.py`
- `apps/api/app/modules/source_discovery/domain/provider.py`
- `apps/api/app/modules/source_discovery/app/services/source_discovery_service.py`
- `apps/api/app/modules/source_discovery/port/local/protocols.py`
- `apps/api/app/modules/source_discovery/port/http/router.py`
- `apps/api/app/modules/source_discovery/container.py`
- `apps/api/app/modules/dataset_collections/`
- `apps/api/app/modules/automations/adapter/sql_repository.py`
- `apps/web/src/features/dataset-collections/presentation/pages/DatasetCollectionDetailView.vue`

`ScSourceRecordProvider` calls `ScUpstreamReader.list_inspections()`, applies the
typed membership-rule condition, and imports matched records through the SC
import port. Live discovery maintains a rule cursor and has receipt, replay,
suppression, source-change, partial-failure, retry, and snapshot-publication
semantics.

Today this path is started through the source-discovery HTTP surface. The
automation overview reports its runs, but there is no recurring upstream poller
that calls live discovery for active collection rules. Therefore the correct
behavioral integration point is the current source-discovery/resource-
automation contract, not a second seed-only event path.

### The upstream list contract lacks an explicit freshness signal

Files:

- `apps/api/app/modules/source_discovery/adapter/sc_provider.py`
- `apps/api/app/modules/sc/adapter/grpc_upstream.py`
- `services/sc-upstream/src/sc_upstream/upstream_db.py`
- `services/sc-upstream/src/sc_upstream/service.py`
- `protos/sc/v1/upstream.proto`

`ScSourceRecordProvider._record()` currently tries to turn `latest_update` into
a `SourceRecord.source_version`. That is the wrong product meaning for an
always-latest source, and the value is not transported consistently anyway:

- `UpstreamDB.list_inspections()` does not select `last_update`.
- `InspectionSummary` in the protobuf has no `latest_update` field.
- `_to_summary_item()` does not map a freshness value.
- `GrpcScUpstream.list_inspections()` cannot restore it.

The replacement is not Dataset versioning. The upstream contract needs only an
inspection-level `last_updated_at` or opaque change token so pollers and caches
can tell whether their current projection is stale. The platform always reads
the newest row and does not persist or expose historical source selection.

## Proposed Target

Create a development-only upstream simulator that behaves like an independently
owned external system:

```text
developer/scenario control
          |
          v
SC upstream simulator ----> dedicated upstream database
          |                         |
          |                         +---- inspection/defect/image metadata
          |                         +---- latest-change/cache freshness token
          |                         +---- publication/readiness state
          |
          +---- gRPC metadata read contract
          +---- Arrow Flight sample stream
          +---- object-store image/zip references
                         |
                         v
API source discovery -> Collection admission/snapshot -> resource automation
```

The simulator should own mutation, transaction, publication, and cache
invalidation. Repository-level seed code may invoke its control API, but must no
longer write the upstream database, zip database, cache directory, or MinIO
metadata independently.

## Candidate Work

### P0: Implement Collection discovery on the internal sensor capability

- Use active Collection membership rules as the supported product surface for
  reacting to upstream SC arrivals.
- Add an internal sensor definition that invokes live discovery for eligible
  active rules every five minutes. Define org/system actor, cursor, retry,
  cancellation, and Task Tracker behavior in that definition.
- Enforce one active run per Collection rule. When the next interval arrives,
  skip and record it if the same rule is still running; do not enqueue a
  duplicate.
- Keep the trigger target-bound and recipe-bound according to
  `CORE_DESIGNS.md`; do not expose arbitrary sensor/workflow subscriptions to
  ordinary users.
- Retain only the internal scheduling/trigger capability from
  `apps/api/app/modules/jobs/sensors`. Remove the legacy timer and dataset-size
  definitions, generic subscription APIs, migrations where safely superseded,
  generated clients, stale documentation, and the unregistered Sensor UI.
- Do not connect a new upstream event to the current exact-equality dispatch
  service; the Collection-discovery sensor calls the resource-discovery
  contract directly.

### P0: Separate production upstream reading from development simulation

Proposed ownership:

- Keep the production-facing gRPC/Flight contract and read service independent
  of platform API internals.
- Move SQLite mock repositories, fixture ORM schema, generators, and simulator
  control behavior out of `services/sc-upstream/src/sc_upstream/` production
  code.
- Put the simulator in a clearly development-only service package or entrypoint,
  such as a service-local `tools/simulator/` package or a separately named
  `devtools/sc-upstream-simulator` service.
- Ensure release images and production Compose/Kubernetes manifests cannot
  import or start the simulator control surface.
- Implement or configure a separate real production upstream adapter only when
  the actual upstream database/driver/schema contract is known. Do not claim
  that the simulator validates production database compatibility.

### P0: Give the simulator its own stateful database

The development Compose stack should start a distinct PostgreSQL database owned
by the simulator instead of bind-mounting repository SQLite files. This models
stateful simulator behavior but does not by itself prove compatibility with an
eventual external production schema.

Required behavior:

- Versioned database schema/migrations owned by the simulator service; this is
  schema evolution, not source-record history.
- Transactional creation of inspection summary, defects, review-image metadata,
  patch-archive metadata, and latest-change time/token.
- Explicit publication/readiness state so readers do not observe a half-created
  inspection. Incomplete-source scenarios are deferred.
- Stable uniqueness rules for inspection identity and defect/image identity.
- Deterministic clocks and IDs when a repeatable scenario requests them.
- Reset only simulator-owned development data; never reset the platform API
  database or shared object-store state implicitly.
- Health/readiness checks that verify both the database and read interfaces.

Completed intermediate slice: `devtools/sc-upstream-simulator` now owns the
initial inspection, defect, review-image, patch-archive, publication, and
change-clock schema. Repository tests verify atomic child-record rollback,
single publication, timezone-aware identity, and change-token allocation. The
same suite has been verified against the migrated PostgreSQL schema. Development
Development Compose wiring, the HTTP control surface, and the gRPC/Flight read
interfaces are complete. The production transport package no longer contains
the SQLite mock schema or adapter, and the development platform reads the
simulator directly.

### P0: Add an explicit development control surface

The simulator needs an intuitive interface for behavior, not only a bulk seed
script. A development-only HTTP control API, used by a thin CLI, initially
supports:

- Create and publish a new inspection at an explicit source time.
- Append deterministic defects and image references before publication.
- Update mutable fields on an existing published inspection and advance its
  latest-change time/token.
- Inspect current records and publication state.

Reset, named timelines, deletion, failure/latency injection, and incomplete or
delayed publication require separate approval before being added.

The control API must bind only in development/test profiles and require an
explicit development credential or private network boundary. The CLI calls the
same API; there is no Make command that reimplements or wraps simulator
behavior.

Completed intermediate slice: the control API now supports atomic draft
creation, pre-publication child append, publication, mutable source updates,
list, and inspect. Every mutation requires the configured bearer credential.
The CLI requires explicit API URL, token, and timeout inputs and communicates
only through HTTP. Local Compose creates the dedicated `sc_simulator` database,
applies migrations, and starts the separately named simulator service; release
manifests do not include it.

### P0: Add a latest-change freshness contract

- Add an inspection-level `last_updated_at` or opaque latest-change token to
  `InspectionSummary` in `protos/sc/v1/upstream.proto`.
- Update the service query and mapping, generated Python/Go protobuf artifacts,
  `GrpcScUpstream`, and source-provider tests.
- Use the value only to invalidate current-state discovery/data-provider caches
  and prevent stale projections. It is not persisted in Dataset identity,
  exposed as a selectable version, or used to pin Collection membership.
- Verify that a mutable source-field change appears on the next resolved read
  without re-import and without `source_changed`/Needs attention behavior.
- Deletion/tombstones are outside the initial simulator and source contract.

Completed: `GetInspectionResponse` and `InspectionSummary` carry the additive
latest-update/change-token fields. This is a current-state freshness signal,
not source versioning. Unit tests cover live adapter reads and an end-to-end
Compose smoke test verified HTTP publication, gRPC metadata, Flight samples,
and an immediately visible mutable-field update.

### P1: Move image and archive generation behind simulator behavior

Relevant current files:

- `devtools/seedmaker/sc_artifacts.py`
- removed legacy `infra/compose/seed_review_images.py`
- `devtools/seedmaker/legacy_sc_sqlite.py`
- `services/image-parser/`

Proposed direction:

- Reuse deterministic image/archive generation code inside the simulator's
  development package.
- Let one simulator publication operation write database metadata and object
  payloads coherently.
- Keep the image-parser as the owner of resolving and serving SC image bytes;
  the simulator only produces upstream-style object references and objects.
- On mutation, invalidate or version upstream caches through an explicit
  service-owned mechanism. Do not clear diskcache directories or restart
  containers from an external script as the consistency protocol.
- Retire overlapping image seed scripts after their unique scenarios and tests
  are migrated.

Completed: `InspectionArtifactPublisher` is simulator-owned and writes the
configured patch/review buckets before the draft is published. Archive and
review metadata are appended to the same simulator inspection. Direct cache
clearing is unnecessary because development reads use the simulator's direct
metadata cache, and the old external artifact generator was removed.

### P1: Reduce `seed-dev` to platform setup plus simulator API calls

Relevant files:

- `make/build.mk`
- `Makefile`
- `scripts/seed.py`
- `devtools/seedmaker/datasets/dev_showcase.py`
- `devtools/seedmaker/dev_activity.py`

Proposed direction:

- Keep `devtools/seedmaker/` responsible for platform-owned development objects
  such as users, Datasets, Collections, rules, and optional display fixtures.
- Replace direct upstream database/object/cache operations with calls to a
  named simulator scenario API.
- Split baseline platform setup from behavioral actions. For example, a
  baseline can create the Collection, connector, profile, and active rule;
  publishing a new upstream inspection should be a separate action that can be
  observed by the automation.
- Stop creating disabled generic sensor subscriptions merely to populate a
  hidden legacy screen.
- Keep non-executing job/model display fixtures separate from end-to-end
  automation scenarios so their fake status does not appear to validate real
  execution.
- Replace duplicated fixture counts, paths, timestamps, and bucket settings
  with scenario-owned inputs and one stable command surface.

Completed: `dev-showcase` invokes the named simulator HTTP scenario, then
creates platform-owned resources through the platform API. It performs no
SQLite, object-store, cache-directory, or container mutation. The old SC fixture
Make targets were removed; developers can invoke the same scenario directly
with the simulator CLI.

### P1: Add behavioral scenarios for source automation

Minimum scenarios:

1. **No new records** — a poll advances or preserves the cursor according to the
   approved rule and creates no Dataset.
2. **New published inspection** — one inspection becomes visible after the
   current cursor, matches a rule, imports once, joins the Collection, and
   publishes at most one Snapshot.
3. **Replay** — polling the same window again does not create a duplicate
   Dataset or member.
4. **Source update** — changing a mutable field advances the freshness token,
   invalidates stale projections, and becomes visible without re-import.
5. **Suppressed record** — a manually removed/suppressed source identity is not
   re-admitted by later polls.
6. **Concurrent polls** — a second tick for the same active rule is skipped and
   recorded, not queued.
7. **Restart durability** — simulator, platform, and worker restarts preserve
   upstream data, freshness tokens, receipts, and cursors.

Delayed/incomplete assets and simulated outage/latency scenarios are deferred
from the initial scope.

### P2: Reconcile documentation and operator tooling

Files:

- `docs/architecture/sensor-pubsub.md`
- `infra/compose/README.md`
- `services/AGENTS.md`
- `apps/api/AGENTS.md`
- Root `AGENTS.md` command documentation

Update the documentation to distinguish:

- Product Resource automations and Collection discovery rules.
- Internal polling/trigger adapters.
- The development upstream simulator.
- The production upstream adapter.
- Platform seed fixtures versus upstream scenario state.

Document one happy-path developer workflow: start the stack, establish a
Collection rule, publish a simulated upstream inspection, observe the automation
run, and inspect the admitted Dataset/Snapshot.

## Explicit Non-Candidates

- Unit-test fakes and in-memory provider stubs remain appropriate for isolated
  tests; not every test should start the simulator.
- Platform users, Collections, jobs, models, annotations, and UI-only display
  activity are not upstream database records and should not move into the
  simulator.
- The simulator must not import API repositories, ORM models, containers, or
  FastAPI dependencies. It communicates through generated contracts and the
  same upstream boundary as a real source.
- The API must not read the simulator database directly.
- A development database engine does not prove compatibility with the unknown
  production upstream database.
- The legacy sensor UI and arbitrary workflow subscriptions should not be
  revived solely to demonstrate the simulator.
- Direct database writes, direct cache-directory deletion, and service restarts
  are not acceptable steady-state simulator mutation APIs.
- Do not add implicit event caps, polling intervals, cursor fallbacks, or retry
  defaults; these require explicit resource-automation decisions and
  observability.

## Proposed Execution Order

1. Retain the internal sensor scheduler while removing the legacy generic
   definitions and user-facing subscription surface.
2. Establish the separate simulator package, PostgreSQL database, publication
   model, and development access control.
3. Complete the latest-change freshness field across the upstream
   protobuf/query/client contract and add contract tests.
4. Add the simulator database schema/migrations and read-only gRPC/Flight
   compatibility tests.
5. Add the HTTP control API and CLI with create/publish, update, and inspect
   operations.
6. Move patch/review object generation and cache invalidation behind simulator
   publication.
7. Wire dev Compose to the simulator and its dedicated database while keeping
   production manifests on the production adapter path.
8. Add the internal resource-automation poller that invokes current live
   discovery semantics.
9. Update `seed-dev` to establish platform objects and invoke simulator
   scenarios; remove migrated direct-write scripts and disabled legacy sensor
   fixtures.
10. Run end-to-end behavioral scenarios, then update architecture and developer
    documentation.

## Acceptance Criteria

- The development stack starts a separately named upstream simulator and its
  owned persistent database without requiring prewritten repository SQLite
  files.
- Developers can publish or update an upstream inspection through one explicit
  simulator control surface without editing databases, object stores, caches,
  or containers manually.
- The API continues to consume the upstream exclusively through its gRPC/Arrow
  contracts.
- New inspection, replay, mutable source update, suppression, concurrency, and
  restart scenarios are deterministic and covered by tests; deferred simulator
  failure modes are not implied.
- The latest-change signal reaches the source and cache boundaries, and mutable
  updates become visible without historical version selection or Needs
  attention behavior.
- Active Collection rules can be evaluated by an internal target-bound
  automation without reintroducing arbitrary user-facing Sensor subscriptions.
- Inspection metadata, sample rows, review-image metadata, patch archives, and
  cache state become visible coherently after publication.
- Production images and manifests cannot expose the simulator control API or
  use mock repositories implicitly.
- `seed-dev` no longer writes upstream SQLite/zip metadata or clears upstream
  caches directly.
- Obsolete sensor YAML/UI/API/deployments and overlapping seed scripts are
  removed or have a documented remaining owner.
- Relevant service tests, API tests, protobuf generation checks, Compose smoke
  tests, `make lint`, and `make test` pass after implementation.

## Before Implementation

The automation direction, overlap policy, PostgreSQL simulator boundary,
HTTP-plus-CLI control surface, initial mutation scope, and always-latest
semantics are approved. Before implementation, inventory the exact legacy
sensor API/generated artifacts to remove and specify the freshness-token and
cache-invalidation contract without introducing source history.
