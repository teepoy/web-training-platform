# Table Widget Interaction Protocol

This document defines a general interaction protocol for sidebar widgets that render tabular or table-like collections. It is intentionally broader than scatter-to-table linking so the same rules can be reused by data tables, scatter plots, sample viewers, and other list-oriented widgets.

This is a protocol and documentation change only. It does not imply that the runtime implementation already exists.

## Scope

Use this protocol when a widget needs to:

- expose stable row or item identity
- select one or more rows or items
- reflect selection created by another widget
- filter visible rows or items from shared interaction state
- link a table to another collection widget such as a scatter plot

This protocol is designed for the classify sidebar widget system, but the state model is generic enough to reuse on future surfaces.

## Design Goals

- keep the current typed widget intent model intact
- define table behavior without assuming any one visualization library
- make row identity explicit instead of inferring it from visible cells
- separate selection from filtering so widgets can highlight without hiding
- support bidirectional linking across widgets through shared interaction state

## Core Concepts

### Collection

A named logical set of rows or items that multiple widgets can reference.

Examples:

- `samples-primary`
- `predictions-review`
- `cluster-members`

Widgets only synchronize when they point at the same collection key.

### Entity Type

The type of object represented by each row or item.

Allowed initial values:

- `sample`
- `prediction`
- `row`

`row` is the generic fallback for table-only datasets that do not map directly to a platform entity.

### Stable Row ID

Every interactive row must have a stable `id`.

Rules:

- `id` must be present on every row
- `id` must be unique within the collection
- `id` must remain stable across sort changes
- `id` must not depend on viewport order or filtered position

Without a stable `id`, a widget must behave as non-interactive.

## Shared Interaction State

The existing interaction state already carries label filter state. This protocol extends it with generic collection state.

```ts
interface TableSelectionState {
  ids: string[];
  sourcePanelId: string | null;
  revision: number;
}

interface TableFilterState {
  ids: string[];
  mode: "all" | "selected-only";
  sourcePanelId: string | null;
  revision: number;
}

interface TableCollectionInteractionState {
  entity: "sample" | "prediction" | "row";
  selection: TableSelectionState;
  filter: TableFilterState;
}

interface SidebarWidgetInteractionState {
  activeLabelFilter: string | null;
  selectedLabels: string[];
  collections?: Record<string, TableCollectionInteractionState>;
}
```

### Semantics

- `selection.ids` controls highlighted rows or items
- `filter.ids` controls which rows or items are visible when filtering is enabled
- selection and filter are related but not equivalent
- a widget may follow selection only, filter only, or both

## Widget Config Contract

Widgets that opt into the protocol should accept a shared `config.interaction` block.

```json
{
  "interaction": {
    "collection": "samples-primary",
    "entity": "sample",
    "emitSelection": true,
    "followSelection": true,
    "filterFromSelection": false,
    "clearFilterOnEmptySelection": true
  }
}
```

### Fields

| Field | Type | Meaning |
|------|------|---------|
| `collection` | string | Shared collection key used for widget linking |
| `entity` | string | Entity type for the rows or items |
| `emitSelection` | boolean | Whether user actions from this widget dispatch selection intents |
| `followSelection` | boolean | Whether this widget highlights rows from shared selection state |
| `filterFromSelection` | boolean | Whether this widget derives row visibility from shared filter state |
| `clearFilterOnEmptySelection` | boolean | Whether empty selection should reset filtering back to all rows |

## Row Data Shape

The current generic `data-table` inline payload uses `columns: string[]` and `rows: any[][]`. That shape is not enough for linked table interactions because row identity is implicit.

For interactive tables, use an explicit row-object shape instead.

```json
{
  "inline": {
    "columns": [
      { "key": "id", "label": "Sample ID" },
      { "key": "label", "label": "Label" },
      { "key": "score", "label": "Score" }
    ],
    "rows": [
      {
        "id": "sample-1",
        "cells": {
          "id": "sample-1",
          "label": "cat",
          "score": 0.98
        },
        "metadata": {
          "sample_id": "sample-1"
        }
      }
    ]
  }
}
```

### Notes

- `cells` is the display payload
- `id` is the stable interaction key
- `metadata` is optional and reserved for widget-specific behavior such as focus, navigation, or tooltips

## Intent Mapping

This protocol reuses the existing typed interaction vocabulary rather than adding table-specific event names.

### Selection intents

Use:

- `select-samples`
- `select-predictions`
- `select-labels` only for label widgets, not row widgets

For generic row data that does not map to platform entities yet, use the closest supported intent and set `metadata.entity = "row"` until the typed vocabulary expands.

Example:

```json
{
  "type": "select-samples",
  "operation": "replace",
  "values": ["sample-1", "sample-2"],
  "sourcePanelId": "nearest-neighbors-table",
  "metadata": {
    "collection": "samples-primary",
    "entity": "sample",
    "target": "selection",
    "revision": 4
  }
}
```

### Filter intents

Use `apply-filter` for row visibility changes.

Example:

```json
{
  "type": "apply-filter",
  "operation": "replace",
  "values": ["sample-1", "sample-2"],
  "sourcePanelId": "embedding-scatter",
  "metadata": {
    "collection": "samples-primary",
    "entity": "sample",
    "target": "filter",
    "filterMode": "selected-only",
    "revision": 5
  }
}
```

### Clear intents

Use `clear-selection` with `operation: "clear"`.

Example:

```json
{
  "type": "clear-selection",
  "operation": "clear",
  "values": [],
  "sourcePanelId": "nearest-neighbors-table",
  "metadata": {
    "collection": "samples-primary",
    "entity": "sample",
    "target": "both",
    "revision": 6
  }
}
```

## User Interaction Semantics

Interactive table widgets should follow the same shared multi-selection rule already documented for sidebar widgets.

- plain click means replace
- Cmd/Ctrl-click means toggle
- drag or range interaction means replace unless a modifier is held
- modifier plus drag or range interaction means union
- clearing selection should not silently clear filters unless the intent explicitly targets filter state as well

### Table-specific guidance

- row checkbox click toggles one row
- plain row click replaces selection with that row
- header checkbox may be used for visible-row bulk selection if the table supports it
- sorting must not discard selection
- filtering must not discard hidden selection unless the action explicitly means replacement

## Rendering Rules

### Table widget

If `followSelection` is enabled:

- highlight rows whose `id` is in shared selection state

If `filterFromSelection` is enabled:

- when filter mode is `selected-only`, show only rows whose `id` is in shared filter state
- when filter mode is `all`, show all rows

Recommended default:

- empty selection with `clearFilterOnEmptySelection: true` resets the table to all rows

### Non-table widgets consuming the same collection

Any linked widget should use the same `collection` and same stable IDs.

Examples:

- scatter plot highlights points whose IDs are selected in the table
- sample viewer highlights or narrows visible samples
- metric widget shows aggregate values for selected rows only

## Loop Prevention

Widgets must not create interaction loops.

Rules:

- widgets emit intents only on direct user action
- widgets may render from shared interaction state without re-emitting
- reducers should track `sourcePanelId` and `revision`
- a widget should ignore its own state update for emission purposes, but still render it

## Compatibility Notes

### Current `data-table` widget

The current `data-table` contract is display-only. It renders:

- `columns: string[]`
- `rows: any[][]`

That shape is still valid for non-interactive tables.

### Interactive table mode

When the table opts into this protocol, prefer the row-object shape with explicit row IDs. A widget may support both modes:

- passive mode: legacy array rows
- interactive mode: explicit row IDs plus `config.interaction`

## Recommended Reducer Responsibilities

The page-level interaction reducer should:

1. resolve the target collection from `intent.metadata.collection`
2. update collection selection state for `select-*` intents
3. update collection filter state for `apply-filter`
4. clear one or both states for `clear-selection`
5. preserve unrelated collection state when one collection changes
6. preserve existing label filter behavior unchanged

## Minimum Author Checklist

When building an interactive table widget later:

1. declare `interaction-state` in `contract.capabilities.reads`
2. declare emitted intents in `contract.capabilities.emits`
3. require stable row IDs for interactive mode
4. document whether the widget emits selection, filter, or both
5. add self-tests for:
   - row click replacement
   - Cmd/Ctrl row toggle
   - sort preserving selection
   - filter preserving hidden selection until explicit replacement

## Current Status

This protocol is documented but not implemented in the runtime today.

At the time of writing:

- `label-distribution` is the only live interactive sidebar widget
- `data-table` is display-only
- `echarts-generic` is display-only
- `interaction-state` currently carries label filter state only

Implementation should extend the existing typed interaction system rather than introducing a separate event bus.
