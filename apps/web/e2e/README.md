# apps/web/e2e — Playwright Test Infrastructure

This is the single home for Playwright configuration, E2E source, and ignored
runtime artifacts. Vitest helpers remain under `src/testing/`. No `.spec.ts`
files live in this root; they belong under `specs/`.

Generated auth state, HTML reports, traces, screenshots, videos, and raw test
results are written only to `.artifacts/`. The directory is gitignored.

## Directory Contract

### `fixtures/`

Playwright `test.extend()` fixtures that wire up shared dependencies
for E2E and integration tests. Includes auth session fixtures,
API-mock fixtures, seed data fixtures, and any data-scoped lifecycle
hooks. Each fixture file exports a typed fixture object for composable
reuse across spec files.

### `seed/`

Orval-typed helpers for live-mode tests that interact with a real
backend. These helpers MUST use the generated orval API client, not
raw `fetch()` calls. Keeps test API calls consistent with the
application's typed contracts.

### `mocks/handlers/`

Playwright `page.route()` handler definitions for `@mock`-tagged
specs. Each handler file intercepts a specific API endpoint group
(e.g. `datasets.ts`, `jobs.ts`, `auth.ts`) and returns canned or
factory-generated responses. Handlers are composable so they can be
combined per test scenario.

### `mocks/factories/`

Typed test data factories built on top of orval-generated model types.
Factories produce minimal valid instances with optional overrides,
making it easy to set up specific test states without verbose inline
object construction.

### `pages/`

Page Object Models (POMs) that mirror the component hierarchy under
`src/features/`. Each POM encapsulates selectors, actions, and
assertions for a single page or major component, keeping spec files
focused on test logic rather than DOM traversal.

### `specs/`

Feature-organized test files. Subdirectories mirror the application
feature structure:

- `auth/` — login, logout, session, permissions
- `datasets/` — list, detail, import, view switching
- `classify/` — annotation, grid, sidebar, agent interaction
- `training/` — job list, detail, start, metrics
- `schedules/` — CRUD, pause/resume, run history
- `preview/` — prediction review, exported preview
- `agent/` — chat drawer, skill triggers
- `dashboard/` — home, aggregate widgets
- `sc/` — study-campaign flows
- `infra/` — health check, error boundaries, routing

### `helpers/`

Miscellaneous utility functions shared across test files:

- Date/time formatting and comparison
- Job polling helpers (wait for terminal state)
- Assertion utilities
- Test-scoped data transformers

### `scripts/`

Node scripts run outside the test runner, such as:

- `check-parity.ts` — validate OpenAPI sync between frontend types and
  the backend contract
- Data seeding or migration scripts for CI environments

### `legacy/`

Excluded pre-redesign scenarios retained as migration references. The runner
collects only `specs/`; a legacy test must be updated to the current UI/API
contract and moved into `specs/<feature>/` before it can be re-enabled.

## Smoke Profile

The `@smoke` tag identifies lightweight, fast tests that validate critical
path functionality. Smoke tests are always `@mock`-mode (no backend required)
and must complete in **≤5 minutes** total.

### Current smoke-tagged specs

| Spec                             | What it verifies                                           |
| -------------------------------- | ---------------------------------------------------------- |
| `specs/infra/api-prefix.spec.ts` | No duplicated `/api/v1/api/v1/` prefix in API request URLs |

Run the smoke profile with:

```bash
pnpm --filter web test:e2e:smoke
```

More specs may be added to the smoke profile over time by tagging them with
`@smoke` in addition to `@mock`. Keep additions light — each smoke test
should complete in under 30 seconds so the whole profile stays fast.

## Conventions

- Orval-typed helpers and factories live in `seed/` and
  `mocks/factories/` respectively; raw fetch calls are forbidden in
  both.
- Do NOT create an `e2e/utils/` directory — use `helpers/` instead.
- Do NOT add a separate `e2e/package.json` — the web workspace
  root `package.json` provides all dependencies.
- Page Objects go in `pages/`, not co-located with specs.
- Spec files use the naming pattern `*.spec.ts` and are organized
  under `specs/<feature>/`.

## Timeout Policy

`timeouts.ts` is the only place for shared timeout budgets:

- ordinary mock tests fail after 30 seconds;
- ordinary live tests fail after 2 minutes;
- Agent QA gets a 5-minute test budget and a 4-minute response budget;
- UI assertions, actions, and navigation keep short independent budgets;
- SC import, training, prediction, and full-workflow tests opt into named
  operation budgets because they launch real backend work;
- the first DuckDB/Arrow materialization of a 300k SC dataset has its own
  `PLAYWRIGHT_SC_DATA_LOAD_TIMEOUT_MS` budget (3 minutes by default);
- live tests run with one Playwright worker to avoid concurrent 300k imports
  competing for the same API and data-provider memory.

Slow acceptance hosts may override a named value with its corresponding
`PLAYWRIGHT_*_TIMEOUT_MS` environment variable. Avoid inline multi-minute
literals in specs and page objects.

The default Compose dev profile disables authentication. Auth-only live tests
therefore skip unless `PLAYWRIGHT_AUTH_ENABLED=1` is supplied for a stack where
both the frontend route guard and API authentication are enabled. Mock auth
coverage always runs.
