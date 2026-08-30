# ADR 0003: Collection publication records without duplicated member data

**Status:** Accepted (2026-08-15)

## Context

A Dataset Collection has a definition that can change as Datasets are linked,
unlinked, reordered, or selected by membership rules. The platform needs an
auditable answer to "which Collection definition did this run use?" without
copying high-frequency member data into every publication record.

## Decision

- A Collection keeps a mutable head definition and publishes immutable
  Collection Revision records.
- A Collection may be created without members or rules as a Draft. A Draft does
  not publish an empty Revision; Revision #1 appears only after the first
  successful publication with at least one resolved member.
- Users do not manually create Revisions. A successful business operation
  publishes at most one Revision at its commit boundary: a saved batch of
  manual membership edits publishes one, and a completed Discovery or Backfill
  run publishes one.
- Head edits that cannot be published remain visible as pending changes with the
  publication error. The last successful ready Revision stays usable, and users
  may correct the pending definition and Retry.
- Training and prediction persist a concrete Collection Revision ID as launch
  provenance instead of reading an unrecorded head definition.
- A Revision records ordered member identities, definition version, rule and
  mapping versions, target contract, trigger, and creation audit. It does not
  record observed Dataset Revision IDs, member row/label counts, or copied
  member data.
- Classify, training, and prediction resolve current member Dataset rows,
  annotations, predictions, and mutable upstream values at operation start.
- A runtime may build a fully materialized Collection view as a performance
  cache, but that cache is derived and reclaimable. It is not retained Revision
  data.
- Historical Revision records can be inspected and used as definitions but
  never edited.
- When the resolved member/rule definition equals the current Revision,
  publication completes as `unchanged` and does not publish an indistinguishable
  Revision. Dataset content or upstream-value changes are not definition
  changes.

## Consequences

- A Collection can evolve without losing the definition provenance of an
  existing Model or job; member data always follows current values and is not
  replayable through the Revision.
- Draft Collections support configuration before data admission; training and
  prediction remain unavailable until a ready Revision exists.
- Failed automation cannot replace a known-good current Revision.
- The UI distinguishes editable Collection rules from published Revisions.
  `Data` summarizes the current definition, `Revisions` provides history, and
  every run links to its concrete Revision. Revisions are not peer resources in
  Library.
- Retention preserves definition audit and job provenance; it does not imply
  retained Dataset payload history.
- Collection publication stays lightweight regardless of member size because
  it never creates per-Revision `data.parquet` or `provenance.parquet` copies.
