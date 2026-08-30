# ADR 0010: Unified Dataset and Collection workspace

**Status:** Accepted (2026-08-15)

## Context

Datasets and Collections are closely related in a user's data-management
journey, but they have different identities and capabilities. A Dataset is an
imported or materialized unit of data; a Collection composes Dataset
memberships and owns rules, Revisions, Model coverage, and resource automation.
Separate sidebar entries make the journey feel fragmented, while one mixed
table would make pagination, statuses, filters, and row actions ambiguous.

## Decision

- The sidebar exposes `Library` / `数据资源库` as the workspace for Dataset and Collection discovery and creation. The generic label `Data` is rejected; Library is a navigation concept, not a third resource type.
- `/library` is the canonical workspace route.
- The workspace contains separate `Datasets` and `Collections` tabs with independent tables and pagination. It does not merge the two domain resources or mix them into one result table.
- Direct navigation to Library opens `Datasets` by default.
- One contextual Create menu offers `Import Dataset` and `Create Collection`. Collection creation supports manual membership, rule-driven membership, or both without creating separate Collection resource types.
- The canonical Dataset and Collection list routes move under `/library`. Existing `/datasets` and `/dataset-collections` list routes redirect to their corresponding tabs; Dataset and Collection detail routes remain resource-specific.
- The active tab and basic query state such as search, creator, and the default current-user scope are URL-addressable. Basic query state is shared when switching tabs; resource-specific advanced filters and pagination remain local to each tab.

## Consequences

- Navigation presents one coherent place to find and create data resources while keeping Dataset and Collection semantics explicit.
- Each tab can preserve its own scalable server query, pagination, columns, bulk actions, and empty states.
- A user can switch between related resource types without losing the basic search context, but a Dataset-only filter cannot silently constrain the Collection table.
- Existing bookmarks to the two list pages continue to land on the matching tab; this route compatibility does not reintroduce legacy Schedule or Sensor redirects.
