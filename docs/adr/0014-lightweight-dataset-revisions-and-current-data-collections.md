# ADR 0014: Lightweight Dataset Revision audit and current-data Collection semantics

**Status:** Accepted (2026-08-15)

## Context

Datasets can change frequently through compatible Re-import, annotation
synchronization, or batch edits. A per-change frozen data copy would add
substantial storage and publication cost before the product has a concrete
reproducibility requirement. Collections need immutable member/rule definition
provenance without copying every member's data into every publication record.
Content fingerprints and historical bulk backfill remain out of scope.

## Decision

- Dataset is a stable logical resource with automatically published lightweight Dataset Revision audit records. Initial successful import publishes Revision #1; compatible Re-import, annotation sync, and batch edit operations publish later Revisions at operation boundaries. Users do not manually manage revisions.
- A Re-import whose output contract is incompatible with the Dataset creates a new Dataset rather than an incompatible Revision.
- A Revision record is immutable, but its first-phase audit manifest references current Dataset storage and explicitly reports `is_reproducible=false`; it does not copy rows, annotations, shards, or images.
- Direct-Dataset training and prediction persist the Dataset Revision observed at
  submission as provenance. A Collection Revision records ordered member and
  rule identity, not observed Dataset Revision IDs.
- Collection classify, training, and prediction resolve current member Dataset
  rows, annotations, predictions, and mutable upstream values at operation
  start. A member Dataset Revision or upstream-value change does not republish
  the Collection Revision and creates no Collection update-review flow.
- Dataset Detail shows the current Revision summary and Revision history. Dataset Revisions do not appear as peer resources in Library.
- Collection Revisions do not archive member rows or Dataset Revision references.
  Optional full materialization is a disposable runtime cache, not retained
  Revision data.
- Existing Datasets receive no bulk schema-data or identity backfill. When a legacy Dataset is first modified or first used by a new revision-aware job, the platform lazily records its then-current state as Revision #1; it does not invent earlier history.

## Consequences

- Dataset identity, Dataset state, and Collection composition have separate lifecycles without requiring image hashing.
- Historical jobs retain which Revision was observed, but exact data reconstruction is not promised in this phase.
- High-frequency Dataset changes add small audit manifests and database records rather than full retained data copies.
- Dataset updates remain visible immediately through current-data resolution;
  they do not publish Collection Revisions or trigger Collection ML work by
  themselves. A failed Collection definition publication leaves the previous
  ready Revision usable.
- Exact reproducibility, if later required, should use an explicit low-frequency frozen Dataset release or versioned storage contract rather than silently changing every audit Revision into a full copy.
