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
| Prop | Type | Default | Role |
|------|------|---------|------|
| `items` | `BrowserItem[]` | `[]` | The flattened list of items to render |
| `totalCount` | `number` | `0` | Total samples available on server |
| `layout` | `'grid' \| 'list'` | `'grid'` | Current display mode |
| `thumbSize` | `number` | `160` | Height of grid cards / list rows |
| `activationMode` | `'open' \| 'select'` | `'open'` | Primary click behavior |
| `selectionEnabled` | `boolean` | `false` | Enables multi-select engine |
| `showCheckboxes` | `boolean` | `false` | Renders checkbox overlays on items |
| `showBottomBar` | `boolean` | `false` | Renders the floating status/action bar |
| `showLabelRail` | `boolean` | `false` | Renders the left-side slot area |

## Shared Preference Persistence (`useSampleBrowserPrefs`)

User presentation choices are persisted to `localStorage` across all surfaces via the `sampleBrowser` Pinia store:

- **Persisted**: `layout`, `thumbSize`, `sidebarCollapsed`.
- **Volatile**: Filters, current selection, and scroll position (reset on navigation).

## Sidebar Shell & Panel Presets

The `BrowserSidebar.vue` component provides a neutral shell for dashboard widgets. It injects a `BROWSER_DASHBOARD_KEY` context that widgets use to resolve stats.

### Panel Presets (`sidebarConfig.ts`)
| Preset | Surface | Purpose | Included Widgets |
|--------|---------|---------|------------------|
| `defaultPanels` | Classify | Full annotation workflow | progress, scatter, viewer, distribution, summary |
| `datasetPanels` | Dataset | Read-only exploration | distribution, scatter (read-only), summary |
| `previewPanels` | Preview | Remote data inspection | distribution, scatter (read-only), summary |

## Surface Responsibilities

| Surface | Core Component | Selection | Primary Action | Sidebar Preset |
|---------|----------------|-----------|----------------|----------------|
| **Dataset** | `DatasetDetailView` | Disabled | Open Drawer | `datasetPanels` |
| **Classify** | `ClassifyView` | Enabled | Toggle Selection | `defaultPanels` |
| **Preview** | `PreviewClassifyView` | Disabled | Open Drawer | `previewPanels` |

## Local Filtering (`useBrowserFilter`)

The `useBrowserFilter` composable provides a pure computed pipeline for filtering loaded items without extra network requests:
1. **Label Filter**: Filters by `activeLabelFilter` matching `currentLabel` or `draftLabel`.
2. **Collection Filter**: Filters by specific ID sets (e.g., "Show Selected Only").

## Key Files

| File | Role |
|------|------|
| `src/components/sample-browser/SampleBrowser.vue` | Shared virtualized browser core |
| `src/components/sample-browser/BrowserSidebar.vue` | Neutral sidebar shell |
| `src/stores/sampleBrowser.ts` | Presentation preference persistence |
| `src/composables/useBrowserFilter.ts` | Browser-scope filtering logic |
| `src/components/classify/sidebarConfig.ts` | Panel registry and surface presets |

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
