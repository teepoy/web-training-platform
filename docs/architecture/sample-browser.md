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

The shared `BrowserSidebar.vue` component in `@platform/web-ui` provides a neutral shell for dashboard widgets. It injects a `BROWSER_DASHBOARD_KEY` context that widgets use to resolve stats. App surfaces pass the plugin component resolver and persisted sidebar width into the shared shell.

### Panel Presets (`sidebarConfig.ts`)
| Preset          | Surface  | Purpose                  | Included Widgets                                       |
| --------------- | -------- | ------------------------ | ------------------------------------------------------ |
| `defaultPanels` | Classify | Full annotation workflow | progress, **wafer-map**, viewer, distribution, summary |
| `datasetPanels` | Dataset  | Read-only exploration    | distribution, **wafer-map**, summary                   |
| `previewPanels` | Preview  | Remote data inspection   | distribution, **wafer-map**, summary                   |

*Note: All surfaces use `wafer-map` for spatial metadata visualization (wafer_x, wafer_y). Classify and Dataset surfaces resolve points via the dataset-level `queryWaferPoints` API, while Preview resolves points from session-loaded item metadata.*

### Wafer coordinate convention

Wafer coordinates (`metadata.wafer_x`, `metadata.wafer_y`) are stored and rendered in **nanometers**, with the wafer disk anchored at the origin and a default radius of `150_000_000 nm` (300 mm wafer). The widget enforces a fixed 1:1 square plotting area at `±150_000_000 nm` on both axes regardless of container aspect ratio, so brush math and the wafer edge stay aligned after sidebar resize. The widget exposes a `waferRadiusNm` config override for non-default wafer geometries; the seed script `scripts/seed_wafer_demo.py` emits coordinates within the default disk via rejection sampling.

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

| File                                               | Role                                |
| -------------------------------------------------- | ----------------------------------- |
| `libs/web-ui/src/components/sample-browser/SampleBrowser.vue` | Shared virtualized browser core     |
| `libs/web-ui/src/components/browser-sidebar/BrowserSidebar.vue` | Neutral sidebar shell               |
| `src/stores/sampleBrowser.ts`                      | Presentation preference persistence |
| `src/composables/useBrowserFilter.ts`              | Browser-scope filtering logic       |
| `src/components/classify/sidebarConfig.ts`         | Panel registry and surface presets  |

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
*Note: E2E tests target `[data-sb-item]` and `[data-sb-id]` attributes for stable element selection.*
