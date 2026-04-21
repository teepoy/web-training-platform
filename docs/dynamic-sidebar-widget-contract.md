# Dynamic Sidebar Widget Contract

The frontend sidebar widget system now has an explicit author contract.

## Source files

- `apps/web/src/components/classify/widgetContract.ts`
- `apps/web/src/components/classify/sidebarConfig.ts`

`widgetContract.ts` defines the shared type vocabulary. `sidebarConfig.ts` remains the registry, but each widget entry now carries author-facing metadata as well as the component reference.

## Required widget contract fields

Each registered widget must define:

- `key`: stable registry key
- `component`: Vue component used at render time
- `contract.displayName`: human-readable widget name
- `contract.description`: short description of the widget purpose
- `contract.acceptsProps`: explicit list of supported props
- `contract.capabilities.reads`: shared contexts the widget consumes
- `contract.capabilities.emits`: typed interaction intents the widget may emit
- `contract.selfTests`: at least one author-facing self-test scenario

## Shared context vocabulary

Supported read contexts are intentionally finite:

- `classify-dashboard`
- `interaction-state`
- `prediction-grid-items`

This keeps widget dependencies discoverable and prevents hidden coupling.

## Typed interaction vocabulary

Supported emitted intents are also intentionally finite:

- `select-samples`
- `select-labels`
- `select-predictions`
- `apply-filter`
- `clear-selection`
- `focus-item`

When interactive widgets are added later, they should use the shared multi-selection rule:

- plain click means replace
- Cmd/Ctrl-click means toggle
- drag means replace unless a modifier is held
- modifier plus drag means union
- filters must not silently drop hidden selection unless the action explicitly means replacement

## Author self-test

Run the lightweight widget contract self-test from the repo root:

```bash
pnpm --dir apps/web test:widgets
```

This test is intentionally small. It validates contract completeness for each registered widget so component authors can catch missing metadata early without booting the whole app.

The first live interaction path is now in `LabelDistributionWidget.vue` on the classify surface:

- clicking a label bar replaces the active dataset label filter
- Cmd/Ctrl-click toggles that one active label on or off
- the widget dims non-active labels and shows a clear chip when a filter is active

This is intentionally limited to a single active server-backed label filter, because the current sample loader and backend query shape only support one label at a time.

Minimum author checklist:

1. Register the widget in `sidebarConfig.ts` using `defineSidebarWidget(...)`.
2. Fill in the contract metadata completely.
3. Add at least one self-test scenario that explains how the widget should be checked.
4. Run `pnpm --dir apps/web test:widgets`.
5. Run `pnpm --dir apps/web build` before merging.
