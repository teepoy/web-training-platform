# Sidebar Extension Guide

How to extend the sample browser sidebar: add new widgets, register new data sources, and wire surface-specific context.

## Architecture Overview

```
BrowserSidebar.vue              ← neutral shell: resize, collapse, panel iteration
  └── WidgetErrorBoundary.vue   ← per-panel crash fence
        └── <YourWidget>.vue    ← Vue component resolved by component key

src/plugins/index.ts            ← explicit widget registration barrel
sidebarConfig.ts                ← per-surface panel presets
@platform/plugin-sdk            ← shared types: intents, interaction context, injection keys
```

The sidebar is data-agnostic. It receives two things from the owning view:

| Prop          | Type                              | Purpose                                                                       |
| ------------- | --------------------------------- | ----------------------------------------------------------------------------- |
| `panels`      | `SidebarPanelDescriptor[]`        | Ordered list of which widgets to show and with what props                     |
| `context`     | `Record<string, unknown>`         | Injected under `BROWSER_DASHBOARD_KEY` for all widgets                        |
| `interaction` | `SidebarWidgetInteractionContext` | Interaction state + dispatch; injected under `SIDEBAR_WIDGET_INTERACTION_KEY` |

---

## Step 1 — Create the Widget Component

Create reusable first-party widgets in `libs/web-ui/src/plugins/sidebar-my-widget/MyWidget.vue`.

Create app-specific widgets in `apps/web/src/plugins/sidebar-my-widget/MyWidget.vue` only when they need app-local API clients, stores, or routes.

### Minimal template

```vue
<!--
  MyWidget — describe what it shows.

  Accepted props (via sidebarConfig descriptor):
    myProp   string   — description (default 'default-value')

  Reads:  browser-dashboard   (via BROWSER_DASHBOARD_KEY inject)
  Emits:  none
-->
<script setup lang="ts">
import { inject } from 'vue'
import { BROWSER_DASHBOARD_KEY } from '@platform/plugin-sdk'

const props = withDefaults(defineProps<{
  myProp?: string
}>(), {
  myProp: 'default-value',
})

// Pull shared context injected by BrowserSidebar
const ctx = inject(BROWSER_DASHBOARD_KEY, {})
</script>

<template>
  <div class="my-widget">
    <!-- render here -->
  </div>
</template>
```

### Reading shared dashboard context

`BROWSER_DASHBOARD_KEY` delivers whatever `Record<string, unknown>` the owning view passed to `BrowserSidebar`'s `:context` prop. The exact keys depend on the surface (see [Surface Context Shapes](#surface-context-shapes) below).

### Reading interaction state

If your widget needs to know the active label filter or react to spatial selections:

```ts
import { inject, computed } from 'vue'
import { SIDEBAR_WIDGET_INTERACTION_KEY } from '@platform/plugin-sdk'

const interactionRef = inject(SIDEBAR_WIDGET_INTERACTION_KEY)
const activeLabel = computed(() => interactionRef?.value.state.activeLabelFilter ?? null)
```

### Emitting interaction intents

To update the shared selection or filter state, call `dispatch` with a `SidebarWidgetIntent`:

```ts
const interactionRef = inject(SIDEBAR_WIDGET_INTERACTION_KEY)

function handleClick(id: string) {
  interactionRef?.value.dispatch({
    type: 'select-samples',       // SidebarWidgetIntentType
    operation: 'replace',          // SidebarWidgetOperation
    values: [id],
    sourcePanelId: 'my-panel-id',
    metadata: {
      collection: 'browser-items', // must match the collection key in config
      entity: 'sample',
      target: 'selection',
    },
  })
}
```

**Intent types:** `select-samples` | `select-labels` | `select-predictions` | `apply-filter` | `clear-selection` | `focus-item`

**Operations:** `replace` | `add` | `remove` | `toggle` | `clear`

**Targets:** `selection` | `filter` | `both`

---

## Step 2 — Export and Register the Plugin Descriptor

Create `libs/web-ui/src/plugins/sidebar-my-widget/index.ts` for reusable widgets:

```ts
import { defineAsyncComponent } from 'vue'
import { defineSidebarPlugin } from '@platform/plugin-sdk'

export const myWidgetPlugin = defineSidebarPlugin({
  key: 'my-widget',
  component: defineAsyncComponent(() => import('./MyWidget.vue')),
  contract: {
    displayName: 'My Widget',
    description: 'One-line description of what it shows.',
    acceptsProps: ['myProp'],
    capabilities: {
      reads: ['browser-dashboard'],
      emits: [],
    },
    selfTests: [
      {
        name: 'renders with minimal props',
        objective: 'Verify the widget shows up without crashing.',
        steps: ['Render without extra props.'],
        expected: ['Widget mounts without errors.'],
      },
    ],
  },
})
```

Export reusable descriptors from `libs/web-ui/src/index.ts`, then import and register the descriptor in `apps/web/src/plugins/index.ts`:

```ts
import { myWidgetPlugin } from '@platform/web-ui'

pluginRegistry.registerSidebarWidget(myWidgetPlugin)
```

---

## Step 3 — Add to a Surface Panel Preset

Choose which surface to add it to, then append a `SidebarPanelDescriptor` to the appropriate array at the bottom of `sidebarConfig.ts`.

| Surface  | Exported constant | Who uses it           |
| -------- | ----------------- | --------------------- |
| Classify | `defaultPanels`   | `ClassifyView`        |
| Dataset  | `datasetPanels`   | `DatasetDetailView`   |
| Preview  | `previewPanels`   | `PreviewClassifyView` |

```ts
export const datasetPanels: SidebarPanelDescriptor[] = [
  // ... existing panels ...
  {
    id: 'my-panel',             // unique per surface; reused as collapse key
    component: 'my-widget',     // must match the registered plugin key
    title: 'My Panel',
    order: 30,                  // lower = higher in the sidebar; default 50
    size: 'compact',            // 'compact' | 'normal' | 'large' — hint for agent panels
    collapsed: false,           // start collapsed?
    props: {
      myProp: 'hello',
    },
  },
]
```

---

## Adding a New Data Source

A data source is just data the owning view injects into the sidebar. There are two patterns:

### Pattern A — Static context (injected once on mount)

Pass computed data through the `BrowserSidebar` `:context` prop:

```ts
// In your view's <script setup>
const mySidebarContext = computed(() => ({
  totalLoaded: items.value.length,
  filteredCount: filteredItems.value.length,
  myCustomStats: { foo: 42 },
}))
```

```html
<BrowserSidebar
  :panels="myPanels"
  :context="mySidebarContext"
  :interaction="myInteraction"
/>
```

In the widget, read it:

```ts
const ctx = inject(BROWSER_DASHBOARD_KEY, {})
const myStats = computed(() => (ctx as any).myCustomStats ?? null)
```

### Pattern B — Inline data in the panel descriptor props

For widgets that need per-panel data that changes over time (e.g. wafer points loaded asynchronously), pass the data through the panel descriptor's `props.data.inline` field and update the descriptor reactively:

```ts
// In your view
const myPanels = computed(() =>
  datasetPanels.map((panel) => {
    if (panel.id !== 'my-panel') return panel
    return {
      ...panel,
      props: {
        ...panel.props,
        data: {
          inline: {
            points: myLoadedPoints.value,  // updated as the query resolves
          },
        },
      },
    }
  })
)
```

The widget then reads `props.data.inline.points` directly:

```ts
const props = defineProps<{
  data?: { inline?: { points?: MyPoint[] } }
}>()
const points = computed(() => props.data?.inline?.points ?? [])
```

---

## The `BrowserItem` Schema

Every item that flows into `SampleBrowser` must conform to `BrowserItem` (defined in `apps/web/src/types.ts`):

```ts
interface BrowserItem {
  id: string                  // unique within the surface
  imageSrcs: string[]         // resolved image URLs
  metadata: Record<string, unknown>
  sourceKind?: 'dataset' | 'preview' | 'classify-review'
  currentLabel: string | null
  draftLabel: string | null
  predictionLabel: string | null
  predictionConfidence: number | null   // 0–1
  predictionId: string | null
  activationLabel: string | null
}
```

Surface adapters in views transform API responses to `BrowserItem`:

```ts
const browserItems = computed<BrowserItem[]>(() =>
  rawSamples.value.map((sample) => ({
    id: sample.id,
    imageSrcs: resolveImageUris(sample.image_uris),
    metadata: sample.metadata ?? {},
    sourceKind: 'dataset',
    currentLabel: sample.latest_annotation?.label ?? null,
    draftLabel: null,
    predictionLabel: null,
    predictionConfidence: null,
    predictionId: null,
    activationLabel: null,
  }))
)
```

`resolveImageUris` is in `src/utils/imageAdapters.ts` — use it for all URI-to-src resolution.

### Metadata convention

Metadata fields used by built-in widgets:

| Field     | Type     | Used by                       |
| --------- | -------- | ----------------------------- |
| `wafer_x` | `number` | `WaferMapWidget` (nanometers) |
| `wafer_y` | `number` | `WaferMapWidget` (nanometers) |

Any additional keys you add to `metadata` are available to custom widgets via `inject(BROWSER_DASHBOARD_KEY)` or directly from items passed down through `props.data`.

---

## Surface Context Shapes

Each surface builds its `context` object differently. Widgets declare which context keys they read in their contract (`capabilities.reads`).

### Dataset surface (`DatasetDetailView`)

```ts
// browserSidebarContext — passed as :context to BrowserSidebar
{
  totalLoaded: number          // items currently loaded in the browser
  filteredCount: number        // items visible after filter
  activeLabelFilter: string | null
  // wafer points are injected via the panel descriptor, not context
}
```

### Classify surface (`ClassifyView` → `ClassifySidebar`)

Widgets can also inject `'classifyDashboard'` (legacy key) which provides the full `ClassifyDashboardContext` from `useClassifyDashboard.ts`.

### Preview surface (`PreviewClassifyView`)

Uses the same `BrowserSidebar` directly with a minimal context similar to the dataset surface. Wafer points come from session-loaded item metadata.

---

## Interaction System

The interaction system coordinates state across sidebar widgets and the main browser grid without prop drilling.

### Key: `SIDEBAR_WIDGET_INTERACTION_KEY`

Injected as a `ComputedRef<SidebarWidgetInteractionContext>`:

```ts
interface SidebarWidgetInteractionContext {
  state: SidebarWidgetInteractionState
  dispatch: (intent: SidebarWidgetIntent) => void
}

interface SidebarWidgetInteractionState {
  activeLabelFilter: string | null
  selectedLabels: string[]
  collections?: Record<string, SidebarWidgetCollectionState>
}
```

### Collection-scoped interaction

For linking a widget to a specific data collection (e.g. spatially selecting samples that filter the browser):

1. Set `config.interaction.collection` in the panel descriptor props to a shared key (e.g. `'browser-items'`).
2. Dispatch intents with `metadata.collection` set to the same key.
3. The owning view's `dispatch` handler calls `reduceCollectionIntent(state.collections, intent)` to update the collection state.
4. `useBrowserFilter` uses the updated collection state to filter the browser grid.

```ts
// In the view's dispatch handler
import { reduceCollectionIntent, reduceLabelFilterIntent } from '../components/classify/widgetContract'

const interaction = computed<SidebarWidgetInteractionContext>(() => ({
  state: interactionState.value,
  dispatch: (intent) => {
    interactionState.value = {
      ...interactionState.value,
      activeLabelFilter: reduceLabelFilterIntent(interactionState.value.activeLabelFilter, intent),
      collections: reduceCollectionIntent(interactionState.value.collections, intent),
    }
  },
}))
```

---

## Wiring a New Surface

To add the sidebar to an entirely new view:

```ts
// 1. Import the shell and a panel preset (or define your own array)
import BrowserSidebar from '../components/sample-browser/BrowserSidebar.vue'
import { datasetPanels } from '../components/classify/sidebarConfig'
import {
  reduceCollectionIntent,
  reduceLabelFilterIntent,
  type SidebarWidgetInteractionContext,
  type SidebarWidgetInteractionState,
} from '../components/classify/widgetContract'
import { useSampleBrowserPrefs } from '../stores/sampleBrowser'

// 2. Prefs for sidebar collapsed state
const prefs = useSampleBrowserPrefs()

// 3. Interaction state
const interactionState = ref<SidebarWidgetInteractionState>({
  activeLabelFilter: null,
  selectedLabels: [],
  collections: {},
})

const interaction = computed<SidebarWidgetInteractionContext>(() => ({
  state: interactionState.value,
  dispatch: (intent) => {
    interactionState.value = {
      ...interactionState.value,
      activeLabelFilter: reduceLabelFilterIntent(interactionState.value.activeLabelFilter, intent),
      collections: reduceCollectionIntent(interactionState.value.collections, intent),
    }
  },
}))

// 4. Context object for widgets
const sidebarContext = computed(() => ({
  totalLoaded: items.value.length,
  filteredCount: filteredItems.value.length,
}))
```

```html
<!-- In the template, alongside SampleBrowser -->
<div style="display: flex; height: 100%">
  <SampleBrowser :items="filteredItems" ... />
  <BrowserSidebar
    :panels="datasetPanels"
    :context="sidebarContext"
    :interaction="interaction"
    :collapsed="prefs.sidebarCollapsed"
    @update:collapsed="prefs.setSidebarCollapsed"
  />
</div>
```

---

## Existing Widgets Reference

| Component key         | File                           | Reads context                             | Emits intents                                                             |
| --------------------- | ------------------------------ | ----------------------------------------- | ------------------------------------------------------------------------- |
| `annotation-progress` | `AnnotationProgressWidget.vue` | `classify-dashboard`                      | —                                                                         |
| `label-distribution`  | `LabelDistributionWidget.vue`  | `classify-dashboard`, `interaction-state` | `select-labels`, `clear-selection`                                        |
| `echarts-generic`     | `GenericEChartsWidget.vue`     | —                                         | —                                                                         |
| `markdown-log`        | `MarkdownLogWidget.vue`        | —                                         | —                                                                         |
| `data-table`          | `DataTableWidget.vue`          | `interaction-state`                       | `select-samples`, `select-predictions`, `apply-filter`, `clear-selection` |
| `metric-cards`        | `MetricCardsWidget.vue`        | —                                         | —                                                                         |
| `sample-viewer`       | `SampleViewerWidget.vue`       | `classify-dashboard`                      | —                                                                         |
| `prediction-summary`  | `PredictionSummaryWidget.vue`  | `prediction-grid-items`                   | —                                                                         |
| `wafer-map`           | `WaferMapWidget.vue`           | `interaction-state`                       | `select-samples`, `select-predictions`, `apply-filter`, `clear-selection` |
| `interactive-scatter` | `InteractiveScatterWidget.vue` | `interaction-state`                       | `select-samples`, `apply-filter`, `clear-selection`                       |
| `browser-summary`     | `BrowserSummaryWidget.vue`     | `browser-dashboard`                       | —                                                                         |

---

## Checklist

- [ ] Widget `.vue` file created in `./widgets/`
- [ ] Descriptor exported from `src/plugins/sidebar-<name>/index.ts`
- [ ] Descriptor registered in `src/plugins/index.ts`
- [ ] `defineSidebarWidget` used (validates contract shape)
- [ ] `contract.capabilities.reads` and `contract.capabilities.emits` accurately declared
- [ ] At least one `selfTests` entry written
- [ ] Panel descriptor added to the target surface preset (`defaultPanels`, `datasetPanels`, or `previewPanels`)
- [ ] If emitting intents: `metadata.collection` set to match the owning view's collection key
- [ ] If injecting context: key documented in this guide under [Surface Context Shapes](#surface-context-shapes)
