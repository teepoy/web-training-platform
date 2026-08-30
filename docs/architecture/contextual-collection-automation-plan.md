# Contextual Collection Automation Implementation Plan

This plan turns ADRs 0001–0014 into incremental, reviewable changes. It is an execution plan, not a replacement for `CORE_DESIGNS.md` or the ADRs.

## Outcomes

- `Library` at `/library` contains separate Dataset and Collection tabs.
- Dataset is a stable resource with lightweight Dataset Revision audit records; no per-Revision data copy, image/content fingerprinting, or historical bulk backfill is introduced.
- Collection Revisions are immutable publications of member identity, ordering, rules, and mappings. They do not pin Dataset Revisions or copy member data.
- Membership rules discover read-only Source records and create Automation-owned Datasets without sharing them across Collections.
- Classify, training, and prediction always resolve current member Dataset rows,
  annotations, predictions, and mutable upstream values. Member data changes do
  not create `Update available` or require another Collection Revision.
- Collection prediction is incremental for newly admitted Datasets and exposes `Current`, `Model mismatch`, `Data outdated`, and `Not predicted` coverage.
- Resource automation is authored from its target resource; existing Schedule/Sensor mechanisms remain internal adapters and their legacy pages receive no redirects.
- Production operator surfaces remain behind explicit Admin configuration and protected infrastructure links.

## Non-goals

- Dataset content hashing, perceptual duplicate detection, or cross-Collection Dataset reuse.
- Historical Dataset identity or Revision backfill.
- Automatic Model promotion, regression evaluation, or arbitrary user-authored workflows.
- A user-facing Partition model or raw cron editor.
- Republishing a Collection Revision when only member Dataset contents or
  upstream values change.

## Phase 1: Dataset Revision foundation

1. Add Dataset Revision persistence and migration without populating historical rows.
2. Publish Revision #1 only for newly completed imports. Lazily create a legacy baseline when an old Dataset first enters a revision-aware write or job flow.
3. Store lightweight audit manifest/provenance references with `is_reproducible=false`; do not copy rows, annotations, or image bytes per Revision.
4. Make annotation synchronization, batch edits, and compatible Re-import publish one Revision at their operation boundary.
5. Extend Dataset APIs with current Revision summary and history. Training and prediction jobs persist the submission-time observed Revision ID as provenance; runtime pinning is deferred.
6. Add Import receipts scoped to the target Resource automation/Collection, Source identity/version, and Import profile version. Replays join, reuse, or Retry the same scoped Import.

## Phase 2: Collection Revision definition

1. Publish one immutable Revision containing ordered member identities and
   versioned mapping/filter/sampling rule identities.
2. Do not store observed Dataset Revision IDs, member row counts, label-count
   caches, or copied member unions on the Collection Revision.
3. Keep the previous ready Revision when publication fails and retain pending
   head-definition changes for correction.
4. Resolve current member data at classify/job start. A complete merge may be a
   disposable runtime cache but is never retained Revision truth.
5. Use stable Collection-safe `row_key`/sample identity for runtime provenance;
   do not use `defect_id` as a cross-inspection identity.

## Phase 3: Dynamic membership and Backfill

1. Add Source connector descriptors, typed provider filter capabilities, Import profiles, Membership rules and immutable rule versions.
2. Add Discovery receipts, scoped Import receipts, Collection-level Source identity deduplication, Membership suppressions, Discovery runs, and explicit time-range Backfill.
3. Implement additive admission, at most one Collection Revision per run,
   partial success, failed-item Retry, pause/resume catch-up choice, and no
   product Partition concept.
4. Use SC as the first provider through a generic Source record contract; SC fields remain inside its descriptor/adapter.

## Phase 4: Collection Model automation

1. Add an exact default Model version binding and compatibility validation against the Collection data contract.
2. Predict only newly admitted Datasets after their membership Revision is
   published.
3. Add tracked bulk reconciliation with one child Prediction Job per Dataset.
4. Record a follow-up TODO for cron-gated Candidate training, named readiness checks, regression safeguards, explicit daily/weekly local-time controls, and no automatic promotion; do not dispatch automated training in this phase.
5. Do not trigger prediction or training from Dataset Revision or upstream-value
   changes alone; only Collection definition/admission changes affect Revision
   publication and reconciliation.

## Phase 5: Information architecture

1. Add `/library`, separate Dataset/Collection tabs, shared URL search/creator scope, independent advanced filters/pagination, and old list-route redirects.
2. Add contextual Collection sections named **Data**, **Models**, **Revisions**,
   and **Activity**, plus a direct `Classify ↗` workspace navigation item with
   no intermediate preview pane.
3. Add Dataset current Revision/history. Do not add Collection member-data
   update review because Collection Revisions always read current member data.
4. Add a global Automations monitoring surface without a targetless creation builder.
5. Add `Admin > Connections` and `Admin > Infrastructure`; do not synthesize localhost external URLs.

## Phase 6: Seed and verification

1. Do not create default display Automation records; exercise real target-bound
   automation from explicit upstream-mock events.
2. Add an explicit deterministic executable scenario for Source discovery,
   Dataset import/Revision, Collection Revision publication, and incremental
   prediction. Candidate training remains a documented follow-up until
   regression safeguards are designed.
3. Verify repeat execution does not duplicate receipts, imports, memberships, runs, or events.
4. Run migrations, generation, lint, pyright, backend tests, web unit/build, route E2E, compose builds where relevant, seed twice, and smoke tests.

## Delivery boundaries

- Each phase is independently migratable and testable.
- API contract changes are generated only after route/schema implementation stabilizes.
- Existing released Dataset/job behavior remains readable. The Collection
  feature is unreleased, so the Revision-only contract has no compatibility
  alias for discarded terminology or fields.
- `CORE_DESIGNS.md` must be updated and its full diff shown before committing architecture changes.
