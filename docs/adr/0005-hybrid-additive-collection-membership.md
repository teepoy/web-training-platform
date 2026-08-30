# ADR 0005: Hybrid additive collection membership

**Status:** Accepted (2026-08-15)

## Context

Manual linking and rule-driven discovery both produce the same underlying
relationship: a Dataset becomes a member of a Collection. Making Manual
Collection and Dynamic Collection separate resource types would duplicate
permissions, Revision publication, training, prediction, and management
surfaces even though only the source of membership differs.

The upstream records used for discovery are read-only. For the SC provider, one Source record is an inspection/wafer/layer summary that can be imported as a Dataset; other providers may define different read-only Source records.

## Decision

- There is one Collection aggregate rather than separate Manual and Dynamic Collection resource types.
- A Collection can contain manually linked members and rule-discovered members at the same time.
- `Dynamic Collection` may be used as a creation shortcut and teaching surface, but it creates the same Collection resource with one or more membership rules.
- A membership rule uses generic Source record identity and provider contracts. SC-specific Patch terminology does not enter the generic Collection or Automation model.
- Manual and rule-discovered members use the same membership lifecycle while recording origin provenance such as manual actor or rule, source, event, and Source record identity.
- First-phase rule evaluation is additive: it can discover, import, and Link new members, but it never automatically Unlinks an existing member when a rule changes or a Source record no longer matches.
- A user may explicitly remove a rule-discovered member. That action creates a suppression keyed by Collection, Source connector, and Source record, preventing any matching rule in that Collection from silently re-adding it until a user clears the suppression; other Collections remain unaffected.
- An already imported Source record that later changes incompatibly is marked
  `Source changed`; it is not silently synchronized in place. A compatible
  Re-import publishes a new Dataset Revision audit record for that
  Automation-owned Dataset; an incompatible output contract creates a new
  Dataset. Existing Collection Revisions read the compatible Dataset's current
  data dynamically and are not republished for its Dataset Revision change.
- Discovery persists a receipt keyed by the membership rule, provider-owned Source record identity, and import profile. Replaying the same receipt returns the first result instead of creating a duplicate. Another rule in the same Collection reuses the Collection member through source-identity deduplication, while another Collection or Resource automation imports its own Dataset from the same Source record.
- One discovery run processes a batch of Source records and publishes at most
  one Collection Revision containing all successfully admitted member
  identities. Individual failures are retained with visible errors and can be
  retried later without blocking successful admissions.

## Consequences

- Collection Detail can present one member list with source badges and filtering instead of separate products.
- Editing or deleting a membership rule stops future discovery but does not silently remove members already admitted by that rule.
- Discovery reports suppressed matches as explainable skips rather than treating them as new, failed, or duplicate imports.
- Dataset import provenance and Collection membership records retain upstream
  identity and Source version so the platform can detect a changed Source
  record without content hashing.
- Rule-driven admission must record enough provider identity to explain why each Dataset entered the Collection.
- Discovery receipts provide exactly-once Dataset creation per rule and Source record despite polling restarts, event redelivery, or request retry.
- A changed Source version or compatible Import profile creates a new Dataset Revision. An incompatible Import profile creates a replacement Dataset; neither case contributes two active rule-derived versions of the Source record to one Collection.
- A partially successful discovery run is visible as partial rather than being
  reported as fully successful; its published Revision contains only member
  identities whose admission completed.
- Membership admission and Collection Revision publication remain separate
  audited steps. Member Dataset or upstream-value changes do not republish the
  Collection Revision.
