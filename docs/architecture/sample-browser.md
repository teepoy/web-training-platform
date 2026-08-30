# Sample Browser Architecture

The shared sample browser system provides a unified interface for exploring, filtering, and selecting data samples across the platform. It is used by the dataset details page, the classification workspace, and the remote data previewer.

## Overview

Instead of fragmented grid implementations, the platform uses a centralized browser core that adapts to different "surfaces" (Dataset, Classify, Preview). Each surface provides its own data loading logic and sidebar context, while sharing presentation preferences and interaction patterns.

## Shared Browser Core (`SampleBrowser.vue`)

The core component handles high-performance rendering and common interaction patterns:

- **Virtualized Rendering**: Uses `@tanstack/vue-virtual` to handle thousands of items with low memory overhead.
- **Layout Modes**: Toggleable "Grid" (thumbnail-first) and "List" (metadata-first) views.
- **Activation Modes**:
  - `open`: Clicking an item emits `open-item` (used for opening detail drawers).
  - `select`: Clicking an item toggles selection (used for batch annotation).
- **Selection Engine**: Support for single-click, ctrl-click (multi-select), and rubber-band (drag-to-select) interactions.
- **Slot Architecture**:
  - `label-rail`: Custom left-side navigation (e.g., classify label buttons).
  - `bar-left` / `bar-right`: Floating bottom bar content for surface-specific actions.

### Component Props

| Prop               | Type                 | Default  | Role                                   |
| ------------------ | -------------------- | -------- | -------------------------------------- |
| `items`            | `BrowserItem[]`      | `[]`     | The flattened list of items to render  |
| `totalCount`       | `number`             | `0`      | Total samples available on server      |
| `layout`           | `'grid' \| 'list'`   | `'grid'` | Current display mode                   |
| `thumbSize`        | `number`             | `160`    | Height of grid cards / list rows       |
| `activationMode`   | `'open' \| 'select'` | `'open'` | Primary click behavior                 |
| `selectionEnabled` | `boolean`            | `false`  | Enables multi-select engine            |
| `showCheckboxes`   | `boolean`            | `false`  | Renders checkbox overlays on items     |
| `showBottomBar`    | `boolean`            | `false`  | Renders the floating status/action bar |
| `showLabelRail`    | `boolean`            | `false`  | Renders the left-side slot area        |

## Shared Preference Persistence (`useSampleBrowserPrefs`)

User presentation choices are persisted to `localStorage` across all surfaces via the `sampleBrowser` Pinia store:

- **Persisted**: `layout`, `thumbSize`, `sidebarCollapsed`, `sidebarWidth`.
- **Sidebar width key**: `sample_browser.sidebar_width` stores the intended expanded width (clamped: MIN=200, MAX=520, DEFAULT=280).
- **Pointer-resize**: The shell uses `setPointerCapture` on the resize handle (`data-testid="browser-sidebar-resize-handle"`) to provide fluid width adjustment.
- **Volatile**: Filters, current selection, and scroll position (reset on navigation).

## Sidebar Shell & Panel Presets

The shared `BrowserSidebar.vue` component in `@platform/web-ui` provides a collapsible sidebar shell. It accepts a `panels` array and a `componentResolver` prop, then delegates all panel rendering to `PanelHost` internally. App surfaces pass the widget component resolver and persisted sidebar width into the shared shell.

`BrowserSidebar` also provides `BROWSER_DASHBOARD_KEY` and `SIDEBAR_WIDGET_INTERACTION_KEY` as a fallback, but pages using the page-level provider model (see below) can pass `:context` and `:interaction` props to share the same reactive state across both in-sidebar and out-of-sidebar widgets.

### Panel Presets (`sidebarConfig.ts`)

| Preset          | Surface  | Purpose                  | Included Widgets                                       |
| --------------- | -------- | ------------------------ | ------------------------------------------------------ |
| `defaultPanels` | Classify | Full annotation workflow | progress, **wafer-map**, viewer, distribution, summary |
| `datasetPanels` | Dataset  | Read-only exploration    | distribution, **wafer-map**, summary                   |
| `previewPanels` | Preview  | Remote data inspection   | distribution, **wafer-map**, summary                   |

_Note: All surfaces use `wafer-map` for spatial metadata visualization (wafer_x, wafer_y). Classify and Dataset surfaces resolve points via the dataset-level `queryWaferPoints` API, while Preview resolves points from session-loaded item metadata._

## Panel Host — Decoupled Panel Rendering

`PanelHost` (`libs/web-ui/src/components/panel-host/PanelHost.vue`) is a standalone component that renders a list of `SidebarPanelDescriptor[]` outside of any sidebar shell. It preserves all panel sub-element rendering: headers, collapse/expand, agent badges, `WidgetErrorBoundary` wrapping, and component resolution via a resolver prop.

When provided with `context` and `interaction` props, `PanelHost` injects `BROWSER_DASHBOARD_KEY` and `SIDEBAR_WIDGET_INTERACTION_KEY` so widgets resolve the same reactive context regardless of whether they sit inside or outside a `BrowserSidebar`.

`BrowserSidebar` now delegates to `PanelHost` internally:

- **Before**: `BrowserSidebar` rendered panels inline with its own provide() calls
- **After**: `BrowserSidebar` delegates to `<PanelHost :panels="panels" :componentResolver="..." :context="context" :interaction="interactionContext" />`

This means any surface can use `PanelHost` directly to render widget panels in an arbitrary page region — a toolbar, a bottom drawer, a floating modal — without a sidebar shell. All CSS selectors (`.cs-panel`, `.cs-panel__header`, etc.) are self-contained in `PanelHost` and do not depend on a `.cs` sidebar wrapper.

## Page-Level Provider Model

Before the decoupling, `BrowserSidebar` owned the `provide()` calls for `BROWSER_DASHBOARD_KEY` and `SIDEBAR_WIDGET_INTERACTION_KEY`. This meant only widgets nested inside the sidebar could inject dashboard context and interaction state.

The new model moves these injection keys to the page root via `usePagePanels`:

### `usePagePanels` composable

**Location**: `libs/web-ui/src/composables/usePagePanels.ts`

Called once per page in `<script setup>`. Provides both keys at page level so any widget anywhere in the component tree can inject the same dashboard context and interaction state:

```ts
const { interactionContext, interactionState, dispatchIntent, dashboard } = usePagePanels({
  dashboardContext: myDashboardContext,
  classifyDashboard?: myClassifyDashboard,  // legacy bridge
  onIntent?: (intent, updatedState) => { /* page-specific side effects */ },
});
```

- `interactionContext` is passed to `BrowserSidebar`'s `:interaction` prop for shared state between in-sidebar and out-of-sidebar widgets
- `dashboard` is a `ShallowReactive<Record<string, unknown>>` kept in sync with the source via `watch` + `Object.assign`
- The optional `classifyDashboard` bridge provides the legacy string key (`"classifyDashboard"`) for widgets that still use it (LabelDistributionWidget, AnnotationProgressWidget)

### `PageProvider` component

**Location**: `libs/web-ui/src/components/page-provider/PageProvider.vue`

For pages built around templates rather than `<script setup>`, `<PageProvider>` wraps `usePagePanels` and exposes the same return values via scoped slot props (`:interaction`, `:dashboard`).

### `useWaferHelpers` composable

**Location**: `libs/web-ui/src/composables/useWaferHelpers.ts`

Shared wafer coordinate utilities extracted from per-surface duplication. Exports:

- `metadataNumber(metadata, key)` — safe numeric extraction from metadata records
- `metadataString(metadata, key)` — safe string extraction from metadata records
- `normalizeWaferPoint(point)` — validates and normalizes a `WaferPoint` (identical logic previously duplicated in ClassifyView and DatasetDetailView)
- `injectWaferPanelData(panels, points, collectionKey?)` — finds the `wafer-map` panel in a descriptor array and injects inline wafer points with the correct collection key per surface

### Adopted pages

Three pages use the new provider model:
| Page | Provider method | Collection key |
|------|----------------|----------------|
| `ClassifyView` | `usePagePanels` in `<script setup>` | `"classify-samples"` |
| `DatasetDetailView` | `usePagePanels` in `<script setup>` | `"browser-items"` |
| `PreviewClassifyView` | `usePagePanels` in `<script setup>` | `"browser-items"` |

### Wafer coordinate convention

Wafer coordinates (`metadata.wafer_x`, `metadata.wafer_y`) are stored and rendered in **nanometers**, with the wafer disk anchored at the origin and a default radius of `150_000_000 nm` (300 mm wafer). The widget enforces a fixed 1:1 square plotting area at `±150_000_000 nm` on both axes regardless of container aspect ratio, so brush math and the wafer edge stay aligned after sidebar resize. The widget exposes a `waferRadiusNm` config override for non-default wafer geometries; upstream-mock scenarios should publish coordinates within the configured geometry.

### Wafer interaction semantics

- The wafer widget emits both selection and filter intents for the configured interaction collection.
- Plain click applies `replace` semantics.
- Cmd/Ctrl-click applies `toggle` semantics and now keeps filter state synchronized with the resulting selection set.
- Brush selection emits `replace` for both selection and filter so linked viewers can narrow to selected IDs.
- `Clear` emits `clear-selection` targeting `both`, resetting selection and filter mode back to `all`.

### Wafer performance notes

- Point rendering stays on ECharts Canvas with progressive large-scatter settings.
- Spatial queries are backed by `KDBush` and operate on ID-preserving point indices.
- Pointer-drag updates and wheel zoom are throttled with `requestAnimationFrame` to reduce event-churn under high point counts.
- Scatter series rows are precomputed in a cached computed payload to avoid repeated map allocations inside chart option assembly.

## Surface Responsibilities

| Surface      | Core Component        | Selection | Primary Action   | Sidebar Preset  |
| ------------ | --------------------- | --------- | ---------------- | --------------- |
| **Dataset**  | `DatasetDetailView`   | Disabled  | Open Drawer      | `datasetPanels` |
| **Classify** | `ClassifyView`        | Enabled   | Toggle Selection | `defaultPanels` |
| **Preview**  | `PreviewClassifyView` | Disabled  | Open Drawer      | `previewPanels` |

## Local Filtering (`useBrowserFilter`)

The `useBrowserFilter` composable provides a pure computed pipeline for filtering loaded items without extra network requests:

1. **Label Filter**: Filters by `activeLabelFilter` matching `currentLabel` or `draftLabel`.
2. **Collection Filter**: Filters by specific ID sets (e.g., "Show Selected Only").

## Key Files

| File                                                            | Role                                                         |
| --------------------------------------------------------------- | ------------------------------------------------------------ |
| `libs/web-ui/src/components/sample-browser/SampleBrowser.vue`   | Shared virtualized browser core                              |
| `libs/web-ui/src/components/browser-sidebar/BrowserSidebar.vue` | Neutral sidebar shell (delegates to PanelHost)               |
| `libs/web-ui/src/components/panel-host/PanelHost.vue`           | Standalone panel renderer — usable anywhere                  |
| `libs/web-ui/src/composables/usePagePanels.ts`                  | Page-level provider for dashboard + interaction keys         |
| `libs/web-ui/src/components/page-provider/PageProvider.vue`     | Template-friendly wrapper for usePagePanels                  |
| `libs/web-ui/src/composables/useWaferHelpers.ts`                | Shared wafer coordinate utilities                            |
| `libs/web-ui/src/components/<name>/`                            | Widget .vue components (12 widgets, moved from plugins/)     |
| `libs/web-ui/src/plugins/sidebar-<name>/index.ts`               | Thin widget descriptor wrappers (12 widgets, .vue moved out) |
| `apps/web/src/stores/sampleBrowser.ts`                          | Presentation preference persistence                          |
| `apps/web/src/composables/useBrowserFilter.ts`                  | Browser-scope filtering logic                                |
| `apps/web/src/components/classify/sidebarConfig.ts`             | Panel registry and surface presets                           |

### Taxonomy note

Widget implementation (.vue) files now live in `libs/web-ui/src/components/<name>/` — they are general-purpose shared components, not sidebar-specific. The widget descriptors in `libs/web-ui/src/plugins/sidebar-<name>/index.ts` are thin wrappers that import the component and export a `defineDashboardWidget()` descriptor. This separation means widgets can be rendered via `PanelHost` in any page region, imported directly by other components, or registered as sidebar widgets — all from the same source file.

## Testing

### Widget & Composable Tests

Unit tests for core logic (no DOM) using Vitest:

```bash
cd apps/web
pnpm run test:widgets
```

### E2E Integration Tests

Full browser flow verification using Playwright:

```bash
cd apps/web
pnpm run test:e2e
```

_Note: E2E tests target `[data-sb-item]` and `[data-sb-id]` attributes for stable element selection._

## BlinkTable

`BlinkTable` is a shared virtualized comparison table in `@platform/web-ui` (`libs/web-ui/src/components/blink-table/BlinkTable.vue`). It renders rows with a synchronized A/B image blink column using `@tanstack/vue-virtual`, plus a global toggle to show or hide the blink column. Every row must supply `imageA` and `imageB` as resolved URLs (the component does not resolve storage URIs). The composable `useBlinkController` drives the shared blink timer exposed as `BlinkPhase` (`'A' | 'B'`).

Resolved means browser-ready and authenticated. The component does not know about storage URIs, dataset IDs, SC defect IDs, tokens, or organization context. Callers must resolve images before they reach the browser core:

- Generic dataset samples use `resolveImageUri()` / `resolveImageUris()` in `apps/web/src/shared/utils/image-adapters.ts`.
- SC patch/review images use `scPatchUrl()`, `scReviewUrl()`, or `buildScBlinkImageUrls()` in `apps/web/src/features/sc/domain/models.ts`.
- Imported SC sparse dataset image refs use scalar Inspection identity and point at the web-gateway `/api/v1/sc/images/...` alias. Shared browser adapters append auth query parameters before rendering; FastAPI does not proxy these bytes.

**Key types** (from `libs/web-ui/src/types/blink-table.ts`): `BlinkRow` (`id`, `imageA`, `imageB`, `metadata`, `cells`), `BlinkColumnDef` (`key`, `title`, optional `width`), `BlinkTableProps` (`rows`, `columns`, optional `blinkIntervalMs` / `initialBlinkEnabled`).

**Storybook story**: `web-ui/components/BlinkTable` — review new work there before wiring into any surface.

**Status**: component and Storybook only. `BlinkTable` is **NOT** mounted into any dataset detail, classify, or preview page. Integration into a concrete app surface is a separate future task.
