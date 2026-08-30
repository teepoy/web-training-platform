# TODO: Partitioned SC Automation and Multi-Inspection Classification

## Batch Baseline

- Recorded before implementation at commit
  `83db1c1d50242b4086978e07918d80b62c4f7785`.
- **Overall status:** Complete. Partition assignment, automated prediction,
  multi-inspection Collection Classify, Revision semantics, and regression
  verification are complete. The accepted Revision/class-taxonomy corrections
  are recorded in `sc-collection-revision-and-class-taxonomy.md`.

## Requested Outcomes

1. Define an SC upstream routing partition keyed by `layer_id + device` and
   connect it to automated prediction.
2. Automated-prediction assignment is exclusive: users cannot attach a partition
   that is already assigned under the exclusivity rule. One Collection may bind
   multiple partitions.
3. Provide a product surface and durable query model for collecting and reviewing
   automated prediction results.
4. Implement multi-inspection classify without the incorrect unmeasured client
   safety gate.

## Architecture Reconciliation

The current architecture uses target-bound Resource automations and removed the
old generic Sensor/Subscription product subsystem. It also states that internal
backfill execution windows are not product Partitions. This work must therefore
either:

- define a new admin-owned SC source-routing partition that is distinct from
  backfill execution windows and remains an implementation detail of a
  target-bound automation recipe; or
- explicitly revise the Resource Automation decision in `CORE_DESIGNS.md` with
  user approval before implementation.

No old generic Sensor builder or unrestricted trigger/action surface may be
restored accidentally.

## Resolved Investigation

- The exact partition key is organization + SC connector + `layer_id + device`.
  The unapproved recipe/dimension alternative was removed.
- Assignment is immutable and transactionally exclusive to one Collection;
  one Collection may own multiple exact partitions.
- The existing five-minute discovery, incremental prediction batches, Activity,
  and per-member Coverage surfaces are reused. No duplicate prediction-facts
  table or materialized view was added.
- Collection Classify resolves one explicit Revision, lets the user select
  multiple members for the shared table/gallery/filter/annotation/job scope,
  and uses one explicitly selected member for the physical map.

## Compatibility and Failure Rules

- Existing released Dataset behavior remains backward-compatible; the
  unreleased Collection feature uses its accepted Revision-only contract
  without a compatibility alias or historical backfill.
- Exclusivity must be enforced by a database constraint or transactional service
  invariant, not only by disabled UI options.
- Partition assignment conflicts fail explicitly and identify the current owner
  to authorized users.
- No client-side sample maximum is imposed without measurement and correct
  server-side counting. The incorrect 300,000-row gate was removed.
- Automated prediction results remain normal platform prediction facts with
  provenance to automation run, Collection Revision, member Dataset, model,
  and stable sample identity.

## Acceptance Criteria

- [x] A versioned partition descriptor and persistence model define exact
      `layer_id + device` membership and overlap semantics.
- [x] One Collection can bind multiple partitions while the approved
      exclusivity invariant is transactionally enforced.
- [x] Five-minute discovery and automatic prediction consume the same partition
      definition; manual prediction remains unaffected.
- [x] Automated results are queried and reviewed across runs without duplicating
      or weakening platform prediction provenance.
- [x] Multi-inspection classify works across selected Revision members and uses
      Collection-safe `row_key`/sample identity rather than `defect_id`.
- [x] Revision publication records member/rule identity and dynamically resolves
      current Dataset and upstream data.

## Implemented Decisions

- An exact partition is Org + SC connector + `layer_id` + `device`. One
  Collection may own many; one exact partition may belong to only one
  Collection.
- Assignment is immutable and transactional. It creates an exact ordinary
  membership rule so the existing five-minute discovery, Revision publication,
  and incremental default-model prediction remain the only execution pipeline.
- Existing prediction batch Activity and per-member Coverage are the durable
  automated-result surfaces. They retain job/model/Revision/member provenance,
  so a second prediction facts table would duplicate state.
- Collection classify is multi-inspection capable through current member
  resolution and Collection-safe row keys. The incorrect 300,000-row browser
  gate and its API/configuration plumbing were removed; no replacement limit
  is imposed in this change.

## Verification

- `make lint` completed successfully: web i18n literals, Ruff, and Prettier
  all passed.
- `make test-web`: 99 test files and 525 tests passed.
- Focused `useReclassifyPage.spec.ts`: 19 tests passed.
- `make build-web` passed.
- Focused mock Playwright Collection Revision/classify flow: 1 test passed.
- Full `make test-e2e`: 50 tests passed.
- `make test`: 1,078 tests passed, 15 skipped, and 1 xpassed; generated OpenAPI
  synchronization passed.
- Full API Pyright completed with 0 errors, and Ruff was clean.
- `make generate` and `make graphify-check` passed.
- The Alembic migration applied successfully to the development PostgreSQL
  database.
- `git diff --check` passed.
