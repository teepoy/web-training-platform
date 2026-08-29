# TODO: Separate Mock, Seed, and Demo Code from Production Packages

## Progress

- **Overall status:** In progress; the goal is not complete.
- **Completed intermediate slices:** removed the disposable settings scaffold,
  moved the active SC artifact generator into `scripts/seedmaker/`, retired its
  unused duplicate, and removed the obsolete demo request prefix.
- **Next milestone:** move mock SC database implementations, API storage test
  doubles, and the local training engine out of production package paths.
- **Done when:** every acceptance criterion below is verified. The artifact
  generator move alone does not satisfy the upstream simulator goal.

This document records the current inventory of mock, seed, fixture, demo, and
test-double code that appears in production-oriented package paths. It is an
audit and proposed package split only. No candidate should be moved until its
runtime callers, intended environment, and replacement production adapter are
confirmed.

This cleanup follows the existing repository rules:

- `test` may use SQLite, memory storage, and mocked external services.
- `dev`, `pre-release`, and `prod` must use explicit runtime service boundaries.
- Repository-wide seed implementations belong under `scripts/seedmaker/`.
- Service-local development fixtures belong under the service's `tools/`
  directory.
- Production `app/` and service `src/` packages must not import seed, mock,
  dummy, fake, or fixture implementations.
- Moves preserve existing product behavior and compatibility reads without a
  data backfill. The disposable settings scaffold and deployment wiring are the
  approved exceptions.

## Candidate Inventory

### P0: SC upstream mock database is the deployable implementation

Files and features:

- `services/sc-upstream/src/sc_upstream/upstream_db.py`
  - Defines the production-facing `UpstreamDB` and `InspectionZipsDB` Protocols.
  - Also defines `_MockUpstreamDB`, `_MockInspectionZipsDB`,
    `create_mock_upstream_db()`, and `create_mock_inspection_zips_db()`.
- `services/sc-upstream/src/sc_upstream/models.py`
  - Defines the SQLAlchemy schema used by the mock SQLite upstream and fixture
    seeders.
- `services/sc-upstream/src/sc_upstream/server.py`
  - The normal service entrypoint constructs both mock database implementations
    unconditionally.
- `services/sc-upstream/src/sc_upstream/__init__.py`
  - Exports the mock factories as part of the installable service package.
- `services/sc-upstream/tools/seed_fixtures.py`
  - Is already in the correct development-only directory, but imports the mock
    schema from the production package.
- `services/sc-upstream/tests/test_flight_server.py` and
  `services/sc-upstream/tests/test_seed_fixture.py`
  - Import the mock implementation or schema directly.
- `services/sc-upstream/Dockerfile`,
  `infra/compose/docker-compose.dev.yaml`,
  `infra/compose/production/compose.platform.yaml`, and
  `infra/k8s/sc-upstream-deployment.yaml`
  - Start the same `sc_upstream.server` entrypoint, so the mock implementation
    is not limited to unit tests or local seed workflows.

Proposed ownership:

- Keep the Protocols and transport service in `sc_upstream` production code.
- Move the SQLite mock adapter, its ORM fixture schema, and mock factories into
  a service-local development package under `services/sc-upstream/tools/`.
- Give the mock service an explicit development entrypoint instead of selecting
  it silently from the normal server.
- Add a separately named production adapter/entrypoint and make deployable
  profiles fail when it is not configured.

Blocker before moving:

There is no separate production upstream adapter in the repository today. A
straight move would break the only working SC upstream service. The real
upstream database/provider contract and production adapter must be identified
or implemented first; a mock must not remain the implicit production fallback.

### P0: API in-memory test doubles are imported by production composition

Files and features:

- `apps/api/app/shared/infrastructure/storage/memory.py`
  - Defines `InMemoryArtifactStorage`, used extensively by tests.
- `apps/api/app/shared/context.py`, `apps/api/app/composition.py`,
  `apps/api/app/sc_data_provider_composition.py`,
  `apps/api/app/shared/infrastructure/storage/__init__.py`, and
  `apps/api/app/shared/infrastructure/storage/factory.py`
  - Import or construct `InMemoryArtifactStorage` from the production package.
- `apps/api/config/test.yaml`
  - Selects `storage.kind=memory`; config validation correctly rejects this
    storage kind outside the test profile.

Proposed ownership:

- Move the in-memory implementation to API test support outside `app/`, such as
  `apps/api/tests/support/storage/`.
- Install it through test injector overrides or a test-only application factory,
  rather than importing it from production composition roots.
- Keep the production `ArtifactStorage` Protocol and MinIO/S3 adapter in `app/`.
- Remove duplicated storage factory paths while changing the composition.

### P0: Local execution test engine is wired into production training code

Files and features:

- `apps/api/app/modules/training/adapter/engines/local_kubeflow.py`
  - Defines the test-only `LocalProcessEngine` in the same module as
    `KubeflowTrainingOperatorEngine`.
- `apps/api/app/modules/training/container.py`
  - Imports both classes and constructs `LocalProcessEngine` for
    `execution.engine=local`.
- `apps/api/config/test.yaml` and
  `apps/api/app/core/config.py`
  - Limit the local engine to the test profile.
- `apps/api/app/modules/training/tests/test_training_metrics_events.py`
  - Directly imports the local engine for tests.

Proposed ownership:

- Move `LocalProcessEngine` to `apps/api/tests/support/engines/` and bind it only
  through test composition.
- Split `KubeflowTrainingOperatorEngine` into a production-named module if it is
  still a supported engine; do not leave production code in a file named
  `local_kubeflow.py`.

### P1: Platform settings endpoint is backed only by an in-memory scaffold

Files and features:

- `apps/api/app/core/settings/adapter/repositories/repository.py`
  - Defines `InMemorySettingsRepository` with process-local volatile state.
- `apps/api/app/core/settings/container.py`
  - Always constructs the in-memory repository.
- `apps/api/app/core/settings/port/http/router.py`
  - Exposes read/write/delete/list operations over that repository.
- `apps/api/app/modules/registry.py`
  - Registers the settings router for the normal API without a test/dev gate.

Resolved disposition:

Treat `/api/v1/settings` as disposable scaffolding and remove it from normal
application registration. The endpoint is arbitrary key/value CRUD backed by a
process-local dictionary, has no persistence or organization ownership, and
has no identified non-generated frontend or API consumer. It is therefore not
a reliable product settings contract. The visible Settings page is unrelated:
it manages access keys through the authentication token APIs and must continue
to work. Removing the generic endpoint is an approved settings compatibility
exception; do not remove or rename the access-key behavior with it.

Completed: the router, in-memory repository, composition wiring, generated API
surface, and obsolete E2E mock were removed. The access-key Settings page and
its authentication-token APIs were left unchanged.

### P1: SC artifact seeders are split between seed and infrastructure code

Files and features:

- `scripts/seedmaker/sc_artifacts.py` (moved from Compose infrastructure)
  - Generates mock SC patch/review image archives, uploads them to MinIO, updates
    the fixture zip database, and clears development caches.
- `scripts/tests/test_seedmaker_sc_artifacts.py`
  - Tests the seeder from the infrastructure package.
- `infra/compose/seed_review_images.py` (removed)
  - Had no repository caller other than its own usage text and duplicated the
    active SC artifact workflow.
- `make/build.mk`
  - Calls `scripts/seedmaker/sc_artifacts.py` from the `seed-wafer-*` targets.
- `infra/compose/README.md`
  - Documents the current script path.

Proposed ownership:

- Move active cross-service SC fixture generation into a dedicated namespace
  below `scripts/seedmaker/`, which is already the repository's canonical seed
  package.
- Keep Compose responsible only for wiring and invoking seed commands.
- The unused `seed_review_images.py` duplicate has been retired rather than
  moved into the new package.
- Update Make targets, tests, and documentation together after the package move.

Completed: the active generator and its tests now live under the repository
seedmaker/scripts namespaces. Compose retains only invocation and service
wiring; the CLI behavior and Make targets remain compatible.

Completion scope: this is package separation only. It does not complete the
stateful upstream simulator goal. The current Make targets and generator still
write SQLite fixture databases, MinIO objects, and cache state directly, while
the normal SC upstream service still constructs mock SQLite repositories. Those
paths remain scheduled for replacement by the separately named PostgreSQL
simulator, its HTTP API/CLI, and API-driven development scenarios recorded in
`stateful-upstream-simulator-and-source-automation.md`.

### P1: Web sandbox/demo pages live in the production feature tree

Files and features:

- `apps/web/src/features/sandbox/router.ts`
- `apps/web/src/features/sandbox/presentation/pages/scenarios/registry.ts`
- `apps/web/src/features/sandbox/presentation/pages/scenarios/classify/ClassifySandboxView.vue`
  - A placeholder page rather than a product feature.
- `apps/web/src/features/sandbox/presentation/pages/scenarios/rchannel-denoise/RChannelDenoiseSandboxView.vue`
  - Depends on a specifically named seeded demo dataset and instructs the user
    to run `make ensure-sandbox-datasets`.
- `apps/web/src/features/sandbox/presentation/pages/scenarios/sampling-rules/SamplingRuleSandbox.vue`
  - Supplies hard-coded sample populations, filters, and counts to a production
    modal.
- `apps/web/src/app/router.ts`
  - Imports the sandbox router from the normal app and conditionally registers
    it with `import.meta.env.DEV`.
- `make/docker.mk`
  - Defines `ensure-sandbox-datasets` for these pages.

Proposed ownership:

- Move the sandbox router and pages outside the production `src/features/`
  domain tree into a dedicated web development package or `apps/web/devtools/`
  entrypoint.
- Load that entrypoint only in development builds; production app modules should
  not import the sandbox package.
- Keep production components consumed by the sandbox in their existing feature
  packages.

### P2: Demo identity remains in API request schemas

Files and features:

- `apps/api/app/modules/datasets/port/http/schemas.py`
- `apps/api/app/shared/api/schemas.py`
- Generated OpenAPI models derived from those schemas.

Both source schema files define `CreateAnnotationRequest.created_by` with the
default `"demo-user"`. The active route ignores the request value and records
the authenticated user instead. This is stale demo contract surface mixed into
business DTOs rather than a reusable test fixture.

Completed action:

- Removed the client-controlled `created_by` field/default from the canonical
  request DTO and deleted the unused duplicate schema. The generated API no
  longer advertises the field, and the web form no longer asks for a value the
  server ignored. Pydantic's existing extra-field behavior continues to accept
  the old property during the compatibility period; route tests retain an old
  request payload as coverage.

### P2: Storybook mock providers sit under shared runtime source

Files and features:

- `apps/web/src/shared/storybook/mocks.ts`
- The Storybook files importing it from shared widget/component directories.

This code is already clearly named and appears to be used only by stories, so it
is lower risk than the candidates above. It should nevertheless be considered
for a Storybook-only support package such as `apps/web/.storybook/support/` if
the build currently includes it in runtime source discovery.

## Explicit Non-Candidates

The following matched search terms but already have appropriate ownership or
are not mocks:

- `scripts/seedmaker/` is the existing dedicated repository seed package.
- `scripts/benchmarks/` is the existing dedicated fake-kernel/benchmark package.
- `services/sc-upstream/tools/seed_fixtures.py` is correctly placed as a
  service-local tool; only its dependency on production mock ORM models needs
  separation.
- `apps/web/e2e/mocks/`, `apps/web/e2e/seed/`, and
  `apps/web/src/testing/` are dedicated test support trees.
- Generated gRPC classes named `*Stub` are transport clients, not test stubs.
- Sampling and ML `seed` parameters control deterministic algorithms; they are
  not fixture seeders.
- `InMemoryArrowDataset` and in-memory DuckDB execution are real bounded data
  processing implementations, not mocks of external services.
- Agent `SessionStore` and `SurfaceStore` hold intentionally ephemeral runtime
  interaction state; they should not be moved as test doubles without a separate
  product decision.

## Proposed Execution Order

1. Define the real SC upstream adapter and the explicit dev mock entrypoint.
2. Move SC mock adapters/models and repair service tests and fixture tooling.
3. Move API in-memory storage and local execution engines behind test-only
   composition.
4. Remove the disposable generic settings router, repository, generated client
   surface, and registration after a final external-consumer check; preserve
   the access-key Settings page and auth token APIs.
5. Consolidate active SC seeders under `scripts/seedmaker/` and retire confirmed
   dead seed scripts.
6. Extract the web sandbox into a dev-only entrypoint/package.
7. Remove stale demo DTO fields and optionally relocate Storybook support.
8. Add boundary tests that inspect symbols and composition imports, not only
   filenames, so `InMemory*` and `LocalProcess*` test doubles cannot return to
   production packages unnoticed.

## Acceptance Criteria

- Production `app/` and service `src/` packages do not define or import mock,
  fake, fixture, seed, demo, or test-double implementations.
- Dev/test implementations are selected explicitly through dev/test entrypoints
  or dependency injection, never as a production fallback.
- Pre-release and production service entrypoints fail clearly when their real
  upstream/storage/runtime adapter is missing.
- Seed commands have one documented package owner and Compose contains only
  environment wiring.
- Web production feature registration does not import the sandbox package.
- Generated API artifacts contain no `demo-user` annotation default.
- The generic volatile `/api/v1/settings` API is absent, while the visible
  access-key Settings page and authentication token APIs retain their behavior.
- Existing dev seeding, unit tests, mock E2E tests, live E2E tests, and relevant
  service checks continue to pass after the moves.
