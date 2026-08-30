# TODO: Make Upstream Mock the Only Development Scenario Surface

## Baseline

- Recorded before implementation at commit `2a24000cb`.
- **Overall status:** Complete.
- This decision supersedes the earlier split where `devtools/seedmaker` owned
  platform showcase objects while the upstream simulator owned only upstream
  rows.

## Goal

Development scenarios must be expressed as upstream behavior through the
standalone Next.js `devtools/upstream-mock` HTTP API, CLI, and tool dashboard.
Starting the platform must not create a seed-named identity, and operational
development workflows must not depend on a second seed CLI or Make target.

The upstream mock remains isolated from production `services/sc-upstream`. It
does not import platform repositories, ORM models, or application services and
does not write the platform database. Platform Datasets, Collections,
predictions, and automation history should appear through real ingestion and
automation behavior after mock upstream events are published.

## Corrected Ownership

- `devtools/upstream-mock` owns mock inspection records, images, named
  scenarios, publication/update actions, and their HTTP/CLI/dashboard controls.
- `services/sc-upstream` owns production cache and gRPC/Arrow behavior and reads
  the mock only through the development adapter.
- Platform identity provisioning is administration, not seeding. It remains an
  explicit `create-superadmin` operation with caller-provided credentials.
- Platform startup and `prepare_platform` create no implicit user, organization,
  Dataset, Collection, Model, annotation, or showcase activity.
- Tests may retain local factories and deterministic data builders under
  clearly test-only ownership. They are not developer-facing seed actions.
- Generic example imports that do not represent upstream behavior must use the
  real product import API/UI or a test fixture; they must not be disguised as an
  upstream scenario.

## Files and Features in Scope

### Operational seed entry points to retire

- `make/build.mk`: `seed` and `seed-dev` targets.
- `scripts/seed.py`: backward-compatible seedmaker wrapper.
- `scripts/dev-init.sh`: implicit/default administrator and dataset seeding.
- `devtools/seedmaker/cli.py`, `runner.py`, and `auth.py`: developer-facing
  registration, promotion, login, organization, and Dataset creation workflow.
- `devtools/seedmaker/datasets/dev_showcase.py` and `dev_activity.py`: direct
  platform showcase creation and fake activity/status records.
- Smoke orchestration that invokes seed commands or assumes a seed account.

### Actions to own in upstream mock

- Deterministic inspection/scenario creation.
- Append/update/publish operations and idempotent replay of named scenarios.
- No bulk reset action is carried forward: mock upstream rows stay stable, and
  the named scenario safely reuses its owned inspection identities.
- Patch/review object fixture publication.
- Tool dashboard and TypeScript CLI calls to the same authenticated HTTP API.
- Behavioral scenarios used to exercise real platform discovery and
  collection automation.

### Identity cleanup

- Remove `seed@example.com`, `seed1234`, and `Seed Admin` as application/devtool
  defaults.
- Remove stale `admin@localhost / admin` claims from `scripts/dev-init.sh` and
  documentation.
- Preserve explicit superadmin provisioning through
  `apps/api/scripts/create_superadmin.py`; it is not part of the upstream mock.
- Existing database rows are not renamed or deleted automatically. No backfill
  is required.

### Test-only compatibility

- Synthetic image/sample builders that are imported only by tests may remain
  temporarily while they are relocated to explicit fixture modules.
- Unit-test fakes, Playwright mocks, and deterministic algorithm RNG seeds are
  not operational seed actions and are outside this move.

## Execution Order

1. Remove seed-owned identity defaults and implicit registration/promotion.
2. Retire Make and script seed entry points, including the platform showcase
   recipe and fake activity generation.
3. Update smoke and developer workflows to require explicit credentials and to
   publish upstream behavior through the mock API/CLI.
4. Relocate remaining test-only builders away from operational seed modules or
   document their fixture-only ownership.
5. Reconcile repository guides, todo completion claims, and Graphify contexts.

## Acceptance Criteria

- `rg` finds no live default for `seed@example.com`, `seed1234`, or `Seed Admin`
  outside historical/audit text and purpose-built regression assertions.
- No Make target or `scripts/seed.py` provides an operational seed surface.
- Every supported upstream mutation/scenario is available through the Next.js
  mock HTTP API and TypeScript CLI/dashboard.
- Starting or preparing the platform creates no implicit identity or showcase
  data.
- The upstream mock never imports or writes platform internals; observed
  platform resources are created by real ingestion/automation flows.
- Explicit administrator provisioning remains documented and tested separately.
- Devtool tests, API tests, smoke contracts, Compose validation, lint, and
  Graphify boundary checks pass.

## Completed Implementation

- Removed the operational `seed` / `seed-dev` Make targets and the stale
  `ensure-mock-datasets` / `ensure-sandbox-datasets` callers.
- Removed the legacy seed CLI, implicit development bootstrap, platform
  showcase/activity writer, direct upstream SQLite writer, and their tests.
- Removed all repository defaults for `seed@example.com`, `seed1234`, and
  `Seed Admin`. Smoke and live Playwright flows now require explicit caller
  credentials.
- Kept `create-superadmin` as a separate administration operation with required
  caller-provided email, password, and display name.
- Reduced `devtools/seedmaker` to deterministic test builders. It has no
  runnable registry, loader, authenticated API client, organization setup, or
  live Dataset creation command.
- Confirmed `devtools/upstream-mock` exposes create, append, publish, update,
  inspect, list, and `dev-showcase` through its HTTP API and TypeScript CLI;
  the dashboard uses the same API.
- Updated development, Compose, extension, and architecture guidance to use
  mock upstream events followed by real platform ingestion and automation.

## Verification

- `make lint`
- `make test`: 1,058 passed, 15 skipped, 1 expected pass; OpenAPI in sync
- `make test-web`: 518 passed
- `make build-web`
- `make test-e2e`: 51 passed
- `make test-regression`: 12 passed, 1 skipped
- `uv run --directory apps/api pyright .`: no errors
- Upstream mock test, lint, typecheck, and production build
- `make check-config`
- `make graphify-check` and rebuilt `ingestion-automation`, `platform-access`,
  and `architecture-contracts`

## Reopened Follow-up: Development Administrator

`make up-dev` must explicitly invoke the separate `create-superadmin`
administration operation after platform preparation. The development identity
is intentionally not owned by upstream-mock scenario tooling. The bootstrap
must be idempotent, dev-only, configurable through dedicated Make variables,
and verified by both a dry-run workflow test and a real login request.

### Follow-up Completion Evidence

- `make up-dev` rebuilds its selected dependencies, restarts image-parser after
  SC upstream is healthy, applies platform migrations, and then converges the
  development superadmin before starting the complete application stack.
- `DEV_SUPERADMIN_EMAIL`, `DEV_SUPERADMIN_PASSWORD`, and
  `DEV_SUPERADMIN_NAME` provide explicit local overrides; the documented
  defaults are `seed@example.com`, `seed1234`, and `Development Admin`.
- `make test-dev-workflow` locks down the targeted parser restart and the
  ordered `prepare-platform` -> `create-superadmin` contract.
- A live `make up-dev` run created or updated the account, and the login API
  returned an access token for that superadmin.
- The complete mock browser suite passes all 51 tests. Verification also closed
  two stale mock boundaries so SC classify limits and Collection-source
  navigation cannot leak fake E2E credentials to the live API and trigger a
  misleading logout.
