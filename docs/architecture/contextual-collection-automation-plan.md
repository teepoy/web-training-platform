# Contextual Collection Automation Implementation Plan

This plan turns ADRs 0001–0014 into incremental, reviewable changes. It is an execution plan, not a replacement for `CORE_DESIGNS.md` or the ADRs.

## Outcomes

- `Library` at `/library` contains separate Dataset and Collection tabs.
- Dataset is a stable resource with lightweight Dataset Revision audit records; no per-Revision data copy, image/content fingerprinting, or historical bulk backfill is introduced.
- Collection Snapshots are immutable publication records that capture observed Dataset Revision IDs without copying all member rows; exact data reproducibility is deferred.
- Membership rules discover read-only Source records and create Automation-owned Datasets without sharing them across Collections.
- Shared Dataset changes show `Update available`; Collection users explicitly refresh to the latest compatible Revision. Refresh does not automatically trigger prediction or candidate training in the first phase.
- Collection prediction is incremental for newly admitted Datasets and exposes `Current`, `Model mismatch`, `Data outdated`, and `Not predicted` coverage.
- Resource automation is authored from its target resource; existing Schedule/Sensor mechanisms remain internal adapters and their legacy pages receive no redirects.
- Production operator surfaces remain behind explicit Admin configuration and protected infrastructure links.

## Non-goals

- Dataset content hashing, perceptual duplicate detection, or cross-Collection Dataset reuse.
- Historical Dataset identity or Revision backfill.
- Automatic Model promotion, regression evaluation, or arbitrary user-authored workflows.
- A user-facing Partition model or raw cron editor.
- Automatic Collection Snapshot refresh when a shared Dataset changes.

## Phase 1: Dataset Revision foundation

1. Add Dataset Revision persistence and migration without populating historical rows.
2. Publish Revision #1 only for newly completed imports. Lazily create a legacy baseline when an old Dataset first enters a revision-aware write or job flow.
3. Store lightweight audit manifest/provenance references with `is_reproducible=false`; do not copy rows, annotations, or image bytes per Revision.
4. Make annotation synchronization, batch edits, and compatible Re-import publish one Revision at their operation boundary.
5. Extend Dataset APIs with current Revision summary and history. Training and prediction jobs persist the submission-time observed Revision ID as provenance; runtime pinning is deferred.
6. Add Import receipts scoped to the target Resource automation/Collection, Source identity/version, and Import profile version. Replays join, reuse, or Retry the same scoped Import.

## Phase 2: Composite Collection Snapshots

1. Record the Dataset Revision IDs observed for every member in each new Snapshot.
2. Represent a Snapshot as a composite logical manifest plus mapping/filter/sampling plans and compact selectors. Full merged Parquet output is a disposable runtime cache, not retained truth.
3. Keep the previous current Snapshot when publication fails and retain pending head changes for correction.
4. Detect newer compatible member Revisions and expose `Update available`; an explicit refresh advances directly to the latest compatible Revisions and publishes at most one Snapshot.
5. Record `Data outdated` when prediction provenance references an older observed Dataset Revision.

## Phase 3: Dynamic membership and Backfill

1. Add Source connector descriptors, typed provider filter capabilities, Import profiles, Membership rules and immutable rule versions.
2. Add Discovery receipts, scoped Import receipts, Collection-level Source identity deduplication, Membership suppressions, Discovery runs, and explicit time-range Backfill.
3. Implement additive admission, one Snapshot per run, partial success, failed-item Retry, pause/resume catch-up choice, and no product Partition concept.
4. Use SC as the first provider through a generic Source record contract; SC fields remain inside its descriptor/adapter.

## Phase 4: Collection Model automation

1. Add an exact default Model version binding and compatibility validation against the Collection data contract.
2. Predict only newly admitted Datasets after their membership Snapshot is current.
3. Add tracked bulk reconciliation with one child Prediction Job per Dataset.
4. Record a follow-up TODO for cron-gated Candidate training, named readiness checks, regression safeguards, explicit daily/weekly local-time controls, and no automatic promotion; do not dispatch automated training in this phase.
5. Keep Dataset-Revision-only Collection refreshes outside automatic prediction and training triggers in the first phase.

## Phase 5: Information architecture

1. Add `/library`, separate Dataset/Collection tabs, shared URL search/creator scope, independent advanced filters/pagination, and old list-route redirects.
2. Add contextual Collection sections: Overview, Data, Models, Snapshots, Activity, plus a direct `Classify ↗` workspace navigation item with no intermediate preview pane.
3. Add Dataset current Revision/history and Collection member update review.
4. Add a global Automations monitoring surface without a targetless creation builder.
5. Add `Admin > Connections` and `Admin > Infrastructure`; do not synthesize localhost external URLs.

## Phase 6: Seed and verification

1. Keep default `seed-dev` Automation records paused/disabled.
2. Add an explicit deterministic executable scenario for Source discovery, Dataset import/Revision, Collection Snapshot, and incremental prediction. Candidate training remains a documented follow-up until regression safeguards are designed.
3. Verify repeat execution does not duplicate receipts, imports, memberships, runs, or events.
4. Run migrations, generation, lint, pyright, backend tests, web unit/build, route E2E, compose builds where relevant, seed twice, and smoke tests.

## Delivery boundaries

- Each phase is independently migratable and testable.
- API contract changes are generated only after route/schema implementation stabilizes.
- Existing job and Snapshot records remain readable through explicit legacy adapters; new behavior never guesses missing historical identity.
- `CORE_DESIGNS.md` must be updated and its full diff shown before committing architecture changes.
