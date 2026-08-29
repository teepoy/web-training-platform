# TODO: Partitioned SC Automation and Multi-Inspection Classification

## Batch Baseline

- Recorded before implementation at commit
  `83db1c1d50242b4086978e07918d80b62c4f7785`.
- **Overall status:** Complete. Exclusive SC routing partitions reuse the
  Collection discovery/prediction pipeline, and multi-inspection classify is
  guarded by a tracked browser cap.

## Requested Outcomes

1. Define an SC upstream routing partition keyed by layer plus device or
   `recipe_id` and connect it to automated prediction.
2. Automated-prediction assignment is exclusive: users cannot attach a partition
   that is already assigned under the exclusivity rule. One Collection may bind
   multiple partitions.
3. Provide a product surface and durable query model for collecting and reviewing
   automated prediction results.
4. Verify whether multi-inspection classify is already technically supported;
   if incomplete, implement it with an explicit configurable client safety cap.

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

## Required Investigation

- Trace Source connector descriptors, Collection membership rules, discovery
  receipts, five-minute polling, automatic prediction batches, coverage, and
  current automation persistence.
- Determine whether `layer + device` and `layer + recipe_id` are alternate
  partition schemas, one composite schema with optional fields, or two registered
  partition descriptors.
- Identify the exact exclusivity owner and database constraint: partition,
  automation recipe, Collection, organization, model binding, or active time
  interval.
- Determine how disabled/archived automations, reassignment, retries, overlapping
  partition definitions, and historical results behave.
- Inventory existing prediction jobs, batch items, Collection coverage, and
  result storage before adding a table or materialized view. Prefer a query/view
  over duplicated prediction facts when it satisfies the product query.
- Trace Collection classify snapshot loading across multiple inspections and
  measure browser memory, Arrow response size, map/gallery rendering, selection,
  and annotation behavior.

## Compatibility and Failure Rules

- Existing Dataset and Collection behavior remains backward-compatible; no
  historical backfill is required unless separately approved.
- Exclusivity must be enforced by a database constraint or transactional service
  invariant, not only by disabled UI options.
- Partition assignment conflicts fail explicitly and identify the current owner
  to authorized users.
- The multi-inspection sample maximum is a tracked YAML setting with no
  environment alias. Exceeding it fails before loading the oversized workbench
  and explains the configured limit.
- Automated prediction results remain normal platform prediction facts with
  provenance to automation run, Collection snapshot, member Dataset, model, and
  stable sample identity.

## Acceptance Criteria

- A versioned partition descriptor and persistence model define layer/device or
  recipe membership and overlap semantics.
- One Collection can bind multiple partitions while the approved exclusivity
  invariant is transactionally enforced.
- Five-minute discovery and automatic prediction consume the same partition
  definition; manual prediction remains unaffected.
- Automated results can be queried and reviewed across runs without duplicating
  or weakening platform prediction provenance.
- Multi-inspection classify works across Collection members and never collides on
  `defect_id`; the explicit configured maximum is tested at below/equal/above
  boundary values.
- Alembic migrations, API contracts, generated clients, UI tests, backend tests,
  and relevant E2E/performance checks pass.

## Implemented Decisions

- An exact partition is Org + SC connector + layer + one alternate dimension
  (`device` or `recipe_id`) + its value. One Collection may own many; one exact
  partition may belong to only one Collection.
- Assignment is immutable and transactional. It creates an exact ordinary
  membership rule so the existing five-minute discovery, snapshot publication,
  and incremental default-model prediction remain the only execution pipeline.
- Existing prediction batch Activity and per-member Coverage are the durable
  automated-result surfaces. They retain job/model/snapshot/member provenance,
  so a second prediction facts table would duplicate state.
- Collection classify was already multi-inspection capable through revision
  materialization and Collection-safe row keys. The tracked
  `sc.data_provider.classify_max_rows` limit is 300,000 total snapshot rows;
  both the route gate and materializer fail rather than truncate above it.
