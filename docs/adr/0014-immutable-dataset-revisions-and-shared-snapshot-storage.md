# ADR 0014: Lightweight Dataset Revision audit and shared Collection manifests

**Status:** Accepted (2026-08-15)

## Context

Datasets can change frequently through compatible Re-import, annotation synchronization, or batch edits. A per-change frozen data copy would add substantial storage and publication cost before the product has a concrete reproducibility requirement. Collections still need an explicit way to notice and record member changes without copying every member's data into every publication record. Content fingerprints and historical bulk backfill remain out of scope.

## Decision

- Dataset is a stable logical resource with automatically published lightweight Dataset Revision audit records. Initial successful import publishes Revision #1; compatible Re-import, annotation sync, and batch edit operations publish later Revisions at operation boundaries. Users do not manually manage revisions.
- A Re-import whose output contract is incompatible with the Dataset creates a new Dataset rather than an incompatible Revision.
- A Revision record is immutable, but its first-phase audit manifest references current Dataset storage and explicitly reports `is_reproducible=false`; it does not copy rows, annotations, shards, or images.
- Training and prediction persist the Dataset Revision observed at submission as provenance. A Collection Snapshot records one observed Dataset Revision for every active member. Runtime loading still resolves current Dataset data in this phase.
- When a shared Dataset publishes a new Revision, every active referencing Collection keeps its current Snapshot and shows `Update available`. Snapshot publication occurs only after an explicit Collection refresh; it does not trigger prediction, reconciliation, or candidate training in the first phase.
- A Collection refresh advances each changed member directly to its latest compatible Dataset Revision. Intermediate Dataset Revisions remain inspectable in Dataset history but do not force intermediate Collection Snapshots.
- Dataset Detail shows the current Revision summary and Revision history. Dataset Revisions do not appear as peer resources in Library.
- Collection Snapshots retain composite logical manifests referencing member Revision audit records rather than archiving copied member rows. Optional full materialization is a disposable runtime cache.
- Existing Datasets receive no bulk schema-data or identity backfill. When a legacy Dataset is first modified or first used by a new revision-aware job, the platform lazily records its then-current state as Revision #1; it does not invent earlier history.

## Consequences

- Dataset identity, Dataset state, and Collection composition have separate lifecycles without requiring image hashing.
- Historical jobs retain which Revision was observed, but exact data reconstruction is not promised in this phase.
- High-frequency Dataset changes add small audit manifests and database records rather than full retained data copies.
- Shared Dataset updates fan out only availability/notification state, not Snapshot publication or ML work. Each Collection may advance independently, and a failed refresh leaves its previous current Snapshot usable.
- Exact reproducibility, if later required, should use an explicit low-frequency frozen Dataset release or versioned storage contract rather than silently changing every audit Revision into a full copy.
