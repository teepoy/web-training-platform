# ADR 0004: Incremental collection prediction and pinned default model

**Status:** Accepted (2026-08-15)

## Context

A rule-driven Collection can discover and link new Datasets over time. Re-running prediction over every existing member whenever one Dataset enters is unnecessarily expensive. At the same time, changing the Collection's preferred Model can leave existing member predictions produced by an older Model, and silently mixing those results would hide inconsistent model provenance.

Automatically promoting every newly trained Model would also allow a regression to replace a known-good model without an evaluation or approval boundary.

## Decision

- A Collection may pin one default Model identity/version for its prediction automation.
- If the pinned default Model is archived, its binding and history remain visible but new automatic or manual Collection prediction is blocked with `Default model unavailable`. The platform never substitutes a Candidate or another Model implicitly.
- Membership discovery and Snapshot publication remain available when no default Model is configured. Newly admitted members are marked `Not predicted`, and no Prediction Job is synthesized from an implicit or recently trained Model.
- When a Dataset newly enters the Collection, automatic prediction processes that new Dataset only. It does not re-run prediction across all existing members.
- When an existing shared Dataset publishes a new Dataset Revision, referencing Collections remain on their current Snapshots and show `Update available`. A user may explicitly refresh a Collection to record the latest compatible member Revisions; that refresh does not automatically run prediction in the first phase. After refresh, the UI must show that prior prediction provenance references an older Dataset Revision rather than presenting it as current.
- Every prediction run and result retains the exact Model identity/version used.
- A Dataset-level incremental prediction remains a Dataset runtime input while separately recording the Automation, Collection, membership, and triggering Snapshot provenance that caused it.
- A newly admitted member is first published in a successful Snapshot. Its incremental Prediction Job is created afterward; prediction failure does not roll back membership or the Snapshot.
- Changing the Collection default Model does not automatically re-predict existing members.
- Setting a default Model after members already exist also does not automatically predict them; the UI presents those members for an explicit reconciliation batch.
- The Collection UI prominently marks member Datasets whose most recent successful prediction attributable to that Collection membership used a Model different from the default Model.
- A member with no successful applicable prediction has a distinct `Not predicted` status rather than being treated as a model mismatch.
- A member whose applicable prediction used an older Dataset Revision has a distinct `Data outdated` status. It is not collapsed into `Model mismatch` or `Not predicted`.
- Users can multi-select mismatched member Datasets and run a tracked reconciliation batch with the current default Model. The batch creates one child Prediction Job per selected Dataset so individual failures can be retried.
- Automated Collection training produces a candidate Model. It does not automatically replace the pinned default Model; evaluation and promotion require a later design decision.

## Consequences

- Incremental prediction cost grows with newly admitted Datasets rather than total Collection size.
- Prediction coverage becomes an explicit, queryable `Current`, `Model mismatch`, `Data outdated`, or `Not predicted` Collection status rather than an assumption.
- The implementation needs Collection-aware provenance for Dataset-level prediction jobs; the current mutually exclusive Dataset versus Collection Revision job source is not sufficient by itself.
- Reconciliation needs a parent batch record in addition to child Prediction Jobs so the UI can show aggregate progress without losing per-Dataset retry and provenance.
- Default-model changes create visible reconciliation work instead of silently rewriting predictions or launching an unbounded full rerun.
- Restoring or replacing an unavailable default Model requires explicit user action before prediction resumes; membership discovery and Snapshot publication continue independently.
