# ADR 0003: Collection publication records without duplicated member data

**Status:** Accepted (2026-08-15)

## Context

A Dataset Collection has a definition that can change as datasets are linked, unlinked, reordered, or selected by future membership rules. The platform needs an auditable answer to "which Collection definition and Dataset changes were observed when this run started?" without copying high-frequency member data into every publication record.

## Decision

- A Collection keeps a mutable head definition and publishes immutable revision records.
- A Collection may be created without members or rules as a Draft. A Draft does not publish an empty revision; `Snapshot #1` appears only after the first successful publication with at least one resolved member.
- Users do not manually create revisions. A successful business operation publishes at most one Snapshot at its commit boundary: a saved batch of manual membership edits publishes one, and a completed Discovery or Backfill run publishes one.
- A successful refresh publishes a new revision and makes it the current revision only after its observed member-Revision manifest and provenance are complete.
- A failed refresh leaves the previous current revision usable.
- Head edits that cannot be published remain visible as pending changes with the publication error. The last successful current Snapshot stays usable, and users may correct the pending definition and Retry rather than losing edits or promoting a failed Snapshot.
- Training and prediction persist a concrete Collection revision ID as launch provenance instead of reading an unrecorded head definition.
- A revision records every resolved member and observed Dataset Revision, definition version, rule and mapping versions, available summaries, a composite manifest, provenance, trigger, and creation audit.
- A Collection Snapshot is a complete publication record, not a physical copy of every member row. Its manifest records lightweight Dataset Revision audit references plus versioned filters, label mappings, sampling, and row-identity plans.
- New records explicitly report `source_resolution=observed` and `reproducibility_capability=false`. They do not claim member payloads are frozen; runtime data is resolved when a run starts.
- Row and label counts are optional aggregate metadata. The archive does not emit a second full copy merely to record counts or provenance.
- A runtime may build a fully materialized Collection view as a performance cache, but that cache is derived and reclaimable. It is not the retained source of truth for Snapshot identity.
- Historical revision records can be inspected and used as definitions but never edited.
- User-facing surfaces call a published revision `Snapshot #N` or `数据快照`; Revision remains the API and persistence term.
- When both the resolved definition and all observed Dataset Revision IDs equal the current Snapshot, refresh completes as `unchanged` and does not publish an indistinguishable Snapshot.

## Consequences

- A Collection can evolve without losing the definition and observed-revision provenance of an existing model or job; exact data replay is deferred.
- Draft Collections support configuration before data admission without presenting an empty Snapshot as a stable training input; training and prediction remain unavailable until a current Snapshot exists.
- Failed automation cannot replace a known-good current snapshot.
- The UI must distinguish editable Collection rules from published data snapshots; it should not require users to reason from opaque revision UUIDs.
- Overview explains and summarizes the current Snapshot, the `Snapshots` area provides history, and every run links to the concrete Snapshot it observed. Snapshots are not peer resources in Library.
- Retention preserves audit manifests and job provenance; it does not imply retained Dataset payload history.
- Ten Collection Snapshots referencing the same Dataset Revision audit record retain small logical references, not ten copied datasets.
- The current implementation's per-Snapshot full `data.parquet` and `provenance.parquet` materialization must be replaced when this design is implemented; otherwise it would duplicate archived data.
