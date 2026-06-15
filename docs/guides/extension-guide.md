# Extension Guide

This document describes the current extension model for the web app and API.

## Frontend extension layout

- Widget implementation (.vue) files: `libs/web-ui/src/components/<name>/<Name>Widget.vue` — general-purpose shared components, not sidebar-specific
- Thin widget descriptor wrappers: `libs/web-ui/src/plugins/sidebar-<name>/index.ts` — import the .vue from `components/<name>/` and export a `defineDashboardWidget()` descriptor
- App-specific sidebar widgets: `apps/web/src/registrations/sidebar-*/index.ts` — same thin-wrapper pattern but app-scoped
- Importers: `apps/web/src/registrations/import-*/index.ts`
- Exporters: `apps/web/src/registrations/export-*/index.ts`
- Preview launchers: `apps/web/src/registrations/preview-*/index.ts`
- Registry singleton: `apps/web/src/core/registry.ts`
- Registration barrel (loaded before mount): `apps/web/src/registrations/index.ts`

Each registration directory exports a named descriptor using SDK helpers:

- `defineDashboardWidget`
- `defineImporter`
- `defineExporter`
- `definePreviewLauncher`
- `defineAgentSkill`

Descriptors are imported and registered in `apps/web/src/registrations/index.ts`.
Descriptors do **not** self-register via side effects — they export descriptors,
and the barrel file calls `widgetRegistry.register*()` explicitly.

SDK package: `libs/widget-sdk/`.
Shared UI and first-party sidebar widgets package: `libs/web-ui/`.

## Sidebar Widgets

The sidebar widget system is a descriptor-driven panel architecture. Widgets can render inside `BrowserSidebar`, standalone via `PanelHost`, or imported directly — all from the same `.vue` source.

### Architecture

```
@platform/web-ui BrowserSidebar.vue ← neutral shell: resize, collapse, panel iteration
  └── WidgetErrorBoundary.vue   ← per-panel crash fence
        └── <YourWidget>.vue    ← Vue component resolved by component key

src/registrations/index.ts            ← explicit widget registration barrel
sidebarConfig.ts                ← per-surface panel presets
@platform/widget-sdk            ← shared types: intents, interaction context, injection keys
```

The sidebar is data-agnostic. It receives from the owning view:

| Prop | Type | Purpose |
|------|------|---------|
| `panels` | `SidebarPanelDescriptor[]` | Ordered list of which widgets to show and with what props |
| `context` | `Record<string, unknown>` | Injected under `BROWSER_DASHBOARD_KEY` for all widgets |
| `interaction` | `SidebarWidgetInteractionContext` | Interaction state + dispatch; injected under `SIDEBAR_WIDGET_INTERACTION_KEY` |

### Widgets are not sidebar-only

Widget .vue components live in `libs/web-ui/src/components/<name>/`, not inside `plugins/sidebar-<name>/`. Widget components are general-purpose shared UI and can be imported directly by other components, rendered via `PanelHost` anywhere, or registered as sidebar widgets — all from the same source file.

`libs/web-ui/src/plugins/sidebar-<name>/index.ts` directories are thin widget descriptors only. They import the component from `components/<name>/` and export a `defineDashboardWidget()` wrapper for the registry-based resolution path.

### Page-level provider model

Pages that need widgets both inside and outside the sidebar call `usePagePanels()` (from `@platform/web-ui`) in `<script setup>`. This composable provides `BROWSER_DASHBOARD_KEY` and `SIDEBAR_WIDGET_INTERACTION_KEY` at the page root, so any widget anywhere in the component tree can inject the same dashboard context and interaction state.

### Step 1 — Create the Widget Component

Reusable first-party widgets go in `libs/web-ui/src/components/<name>/<Name>Widget.vue`. App-specific widgets go in `apps/web/src/registrations/sidebar-<name>/<Name>Widget.vue`.

**Minimal template:**

```vue
<script setup lang="ts">
import { inject } from 'vue'
import { BROWSER_DASHBOARD_KEY } from '@platform/widget-sdk'

const props = withDefaults(defineProps<{
  myProp?: string
}>(), {
  myProp: 'default-value',
})

const ctx = inject(BROWSER_DASHBOARD_KEY, {})
</script>

<template>
  <div class="my-widget">
    <!-- render here -->
  </div>
</template>
```

**Reading interaction state:**

```ts
import { inject, computed } from 'vue'
import { SIDEBAR_WIDGET_INTERACTION_KEY } from '@platform/widget-sdk'

const interactionRef = inject(SIDEBAR_WIDGET_INTERACTION_KEY)
const activeLabel = computed(() => interactionRef?.value.state.activeLabelFilter ?? null)
```

**Emitting interaction intents:**

```ts
const interactionRef = inject(SIDEBAR_WIDGET_INTERACTION_KEY)

function handleClick(id: string) {
  interactionRef?.value.dispatch({
    type: 'select-samples',
    operation: 'replace',
    values: [id],
    sourcePanelId: 'my-panel-id',
    metadata: {
      collection: 'browser-items',
      entity: 'sample',
      target: 'selection',
    },
  })
}
```

**Intent types:** `select-samples` | `select-labels` | `select-predictions` | `apply-filter` | `clear-selection` | `focus-item`

**Operations:** `replace` | `add` | `remove` | `toggle` | `clear`

**Targets:** `selection` | `filter` | `both`

### Step 2 — Export and Register the Widget Descriptor

Each widget must define a contract using `defineDashboardWidget`:

```ts
import { defineAsyncComponent } from 'vue'
import { defineDashboardWidget } from '@platform/widget-sdk'

export const myWidget = defineDashboardWidget({
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

Export reusable descriptors from `libs/web-ui/src/index.ts`, then register in `apps/web/src/registrations/index.ts`:

```ts
import { myWidget } from '@platform/web-ui'
widgetRegistry.registerWidget(myWidget)
```

### Widget Contract Requirements

Each registered widget must define:

- `key`: stable registry key
- `component`: Vue component resolved at render time
- `contract.displayName`: human-readable widget name
- `contract.description`: short description of widget purpose
- `contract.acceptsProps`: explicit list of supported props
- `contract.capabilities.reads`: shared contexts the widget consumes
- `contract.capabilities.emits`: typed interaction intents the widget may emit
- `contract.selfTests`: at least one author-facing self-test scenario

**Shared context vocabulary** (finite set):

- `classify-dashboard`
- `interaction-state`
- `prediction-grid-items`

**Typed interaction vocabulary** (finite set):

- `select-samples` | `select-labels` | `select-predictions`
- `apply-filter` | `clear-selection` | `focus-item`

**Multi-selection rules:**
- Plain click = replace
- Cmd/Ctrl-click = toggle
- Drag = replace unless modifier held
- Modifier + drag = union
- Filters must not silently drop hidden selection unless action means replacement

### Step 3 — Add to a Surface Panel Preset

Append a `SidebarPanelDescriptor` to the appropriate array in `sidebarConfig.ts`:

| Surface | Exported constant | Who uses it |
|---------|-------------------|-------------|
| Classify | `defaultPanels` | `ClassifyView` |
| Dataset | `datasetPanels` | `DatasetDetailView` |
| Preview | `previewPanels` | `PreviewClassifyView` |

```ts
export const datasetPanels: SidebarPanelDescriptor[] = [
  // ... existing panels ...
  {
    id: 'my-panel',             // unique per surface; reused as collapse key
    component: 'my-widget',     // must match the registered widget key
    title: 'My Panel',
    order: 30,                  // lower = higher in sidebar; default 50
    size: 'compact',            // 'compact' | 'normal' | 'large'
    collapsed: false,
    props: {
      myProp: 'hello',
    },
  },
]
```

### Data Source Patterns

**Pattern A — Static context** (injected once on mount):

```ts
// In your view's <script setup>
const mySidebarContext = computed(() => ({
  totalLoaded: items.value.length,
  filteredCount: filteredItems.value.length,
}))
```

```html
<BrowserSidebar :panels="myPanels" :context="mySidebarContext" :interaction="myInteraction" />
```

Read in widget: `const ctx = inject(BROWSER_DASHBOARD_KEY, {})`

**Pattern B — Inline data in panel descriptor props:**

```ts
const myPanels = computed(() =>
  datasetPanels.map((panel) => {
    if (panel.id !== 'my-panel') return panel
    return { ...panel, props: { ...panel.props, data: { inline: { points: myLoadedPoints.value } } } }
  })
)
```

Widget reads: `const points = computed(() => props.data?.inline?.points ?? [])`

### BrowserItem Schema

Every item flowing into `SampleBrowser` must conform to `BrowserItem` (from `@platform/web-ui`):

```ts
interface BrowserItem {
  id: string
  imageSrcs: string[]
  metadata: Record<string, unknown>
  sourceKind?: 'dataset' | 'preview' | 'classify-review'
  currentLabel: string | null
  draftLabel: string | null
  predictionLabel: string | null
  predictionConfidence: number | null
  predictionId: string | null
  activationLabel: string | null
}
```

### Interaction System

The interaction system coordinates state across sidebar widgets and the main browser grid. Injected as `ComputedRef<SidebarWidgetInteractionContext>`:

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

**Collection-scoped interaction** links a widget to a specific data collection:
1. Set `config.interaction.collection` in panel descriptor props (e.g. `'browser-items'`)
2. Dispatch intents with `metadata.collection` set to the same key
3. The owning view's dispatch handler calls `reduceCollectionIntent(state.collections, intent)`
4. `useBrowserFilter` consumes the updated collection state

### Surface Context Shapes

**Dataset surface** (`DatasetDetailView`): `{ totalLoaded, filteredCount, activeLabelFilter }`

**Classify surface** (`ClassifyView`): Also injects `'classifyDashboard'` (legacy key via `useClassifyDashboard`)

**Preview surface** (`PreviewClassifyView`): Minimal context similar to dataset surface; wafer points from session-loaded metadata

### Wiring a New Surface

```ts
// In <script setup>
import { BrowserSidebar } from '@platform/web-ui'
import { datasetPanels } from '../components/classify/sidebarConfig'
import { useSampleBrowserPrefs } from '../stores/sampleBrowser'

const prefs = useSampleBrowserPrefs()
const sidebarContext = computed(() => ({ totalLoaded: items.value.length, filteredCount: filteredItems.value.length }))
```

```html
<div style="display: flex; height: 100%">
  <SampleBrowser :items="filteredItems" ... />
  <BrowserSidebar :panels="datasetPanels" :context="sidebarContext" :collapsed="prefs.sidebarCollapsed" />
</div>
```

### Existing Widgets Reference

| Component key | File | Reads context | Emits intents |
|---|---|---|---|
| `annotation-progress` | `AnnotationProgressWidget.vue` | `classify-dashboard` | — |
| `label-distribution` | `LabelDistributionWidget.vue` | `classify-dashboard`, `interaction-state` | `select-labels`, `clear-selection` |
| `echarts-generic` | `GenericEChartsWidget.vue` | — | — |
| `markdown-log` | `MarkdownLogWidget.vue` | — | — |
| `data-table` | `DataTableWidget.vue` | `interaction-state` | `select-samples`, `select-predictions`, `apply-filter`, `clear-selection` |
| `metric-cards` | `MetricCardsWidget.vue` | — | — |
| `sample-viewer` | `SampleViewerWidget.vue` | `classify-dashboard` | — |
| `prediction-summary` | `PredictionSummaryWidget.vue` | `prediction-grid-items` | — |
| `interactive-scatter` | `InteractiveScatterWidget.vue` | `interaction-state` | `select-samples`, `apply-filter`, `clear-selection` |
| `browser-summary` | `BrowserSummaryWidget.vue` | `browser-dashboard` | — |

### Self-Test

Run the widget contract self-test from repo root:

```bash
pnpm --dir apps/web test:widgets
```

### Widget Checklist

- [ ] Widget `.vue` file created in correct location
- [ ] Descriptor exported via `defineDashboardWidget` (validates contract shape)
- [ ] Descriptor registered in `apps/web/src/registrations/index.ts`
- [ ] `contract.capabilities.reads` and `contract.capabilities.emits` accurately declared
- [ ] At least one `selfTests` entry written
- [ ] Panel descriptor added to target surface preset (`defaultPanels`, `datasetPanels`, or `previewPanels`)
- [ ] If emitting intents: `metadata.collection` set to match the owning view's collection key
- [ ] Run `pnpm --dir apps/web test:widgets` and `pnpm --dir apps/web build`

## Importers (Dataset view)

Dataset import UI is descriptor-driven using a 2-step flow via `FlowModal`:

- Step 1: `FlowTypeSelector` shows available importers as selectable cards
- Step 2: Selected importer component is mounted inside the modal

Importers are discovered with `widgetRegistry.getImporters("dataset")`.

- `DatasetsView.vue` uses `FlowModal` with `kind="import"` for dataset-creation importers (surface: `"dataset"`)
- `DatasetDetailView.vue` uses `FlowModal` with `kind="import"` for sample-level importers (surface: `"dataset"`)

Importer receives `ImporterRequiredProps`:
  - `datasetId`
  - `onComplete`
  - `onCancel`

Examples:

- `apps/web/src/registrations/import-manual/` — single-sample manual entry (surface: `"dataset"`)
- `apps/web/src/registrations/import-dataset-manual/` — JSON bulk import creating a new dataset (surface: `"dataset"`)

## Exporters (Dataset view)

Dataset export UI is descriptor-driven using a 2-step flow via `FlowModal`:

- Step 1: `FlowTypeSelector` shows available exporters as selectable cards
- Step 2: Selected exporter component is mounted inside the modal

Exporters are discovered with `widgetRegistry.getExporters("dataset")`.

Exporter receives `ExporterRequiredProps`:
  - `datasetId`
  - `onComplete`
  - `onCancel`

Examples:

- `apps/web/src/registrations/export-preview/`
- `apps/web/src/registrations/export-persist/`

## Preview launchers (Preview Dataset)

Preview creation is descriptor-driven using a 2-step flow in `PreviewLaunchView.vue`:

- Step 1: `FlowTypeSelector` shows available preview launchers as selectable cards
- Step 2: Selected launcher component renders inline

Launchers are discovered with `widgetRegistry.getPreviewLaunchers("preview")` or `getPreviewLaunchers("dataset-list")`.

Preview launcher receives `PreviewLauncherRequiredProps`:
  - `onComplete(result: { sessionId: string })`
  - `onCancel`

On `onComplete`, the host navigates to `/preview/:sessionId`.

Example: `apps/web/src/registrations/preview-upstream/`

## Backend API extension routes

API extension routers are explicitly registered in:

- `apps/api/app/routers/registry.py`

To add a new backend extension route:

1. Create `apps/api/app/routers/<name>/router.py` with an `APIRouter` named `router`
2. Import it in `apps/api/app/routers/registry.py` and add it to `EXTENSION_ROUTERS`

There are currently no built-in backend extension routes. Existing import and
export flows use the typed frontend API client against core API endpoints.

## Adding a New Sensor

The platform's sensor pub/sub system allows you to trigger workflows based on external data changes. To add a new sensor, follow these steps:

1. **Create a Sensor YAML**: Define your sensor's metadata and filtering capabilities in `apps/api/sensors/<your_sensor_id>.yaml`.
   ```yaml
   id: my_sensor
   name: My Custom Sensor
   description: Monitors an external system for changes
   cron: "*/10 * * * *"
   available_triggers:
     - train
     - predict
   filter_schema:
     type: object
     properties:
       source_name:
         type: string
     additionalProperties: false
   ```

2. **Implement the Prefect Flow**: Create a new flow file in `apps/api/app/flows/<your_sensor_id>.py`. This flow is responsible for polling the data source and sending events to the platform.
   ```python
   from prefect import flow
   import httpx

   @flow
   def my_sensor_flow():
       # 1. Fetch data from source
       # 2. Compare against previous watermark (optional)
       # 3. Build events
       events = [{"source_name": "example", "value": 123}]
       # 4. POST to platform API
       PLATFORM_API_URL = "http://localhost:8000"
       httpx.post(f"{PLATFORM_API_URL}/api/v1/sensors/events", json={
           "sensor_id": "my_sensor",
           "events": events,
           "watermark": {"last_timestamp": "2023-01-01T00:00:00"}
       })
   ```

3. **Register the Deployment**: Open `apps/api/app/flows/serve.py` and add your flow to the `serve` list with the desired cron schedule.

4. **Verification**: Once registered, your sensor will automatically appear in the platform API (`GET /api/v1/sensors`) and the Sensors UI in the web app, where users can create subscriptions for it.

Refer to `apps/api/app/flows/dataset_size_sensor.py` for a complete reference implementation.

---

## 7. Adding a New Dataset Type

A "dataset type" controls how samples, annotations, Label Studio configuration, mock data, and frontend views are shaped. The schema system bundles all of these into one descriptor so nothing gets out of sync.

### Step-by-step

#### Backend

**a. Add enum values** in `apps/api/app/domain/types.py`:
```python
class DatasetType(str, Enum):
    IMAGE_CLASSIFICATION = "image_classification"
    IMAGE_VQA = "image_vqa"
    IMAGE_DETECTION = "image_detection"
    IMAGE_SEGMENTATION = "image_ newsegmentation"   #

class TaskType(str, Enum):
    CLASSIFICATION = "classification"
    VQA = "vqa"
    DETECTION = "detection"
    SEGMENTATION = " newsegmentation"               #
```

**b. Create the schema module** `apps/api/app/domain/schemas/image_segmentation.py`:
```python
from __future__ import annotations
from app.domain.dataset_schema import DatasetSchema
from app.domain.preview import PreviewItem
from app.domain import schema_registry

def _generate_ls_config(label_space: list[str]) -> str:
    # Return Label Studio XML string for segmentation
    ...

def _mock_item_generator(index: int, label_space: list[str]) -> PreviewItem:
    # Return a deterministic PreviewItem (no external I/O)
    ...

SCHEMA = DatasetSchema(
    dataset_type="image_segmentation",
    task_type="segmentation",
    annotation_type="masks",
    label_space_mode="required",
    generate_ls_config=_generate_ls_config,
    platform_annotation_to_ls=...,
    ls_annotation_to_platform=...,
    mock_item_generator=_mock_item_generator,
)
schema_registry.register(SCHEMA)
```

**c. Register in the barrel** `apps/api/app/domain/schemas/__init__.py`:
```python
from app.domain.schemas import image_segmentation  # noqa: F401
```

After this, `compatibility.py` will automatically allow the new pair via `get_allowed_pairs()` and the preview service will use the correct LS config.

#### Frontend

**d. Add type values** in `libs/web-ui/src/api/types.ts`:
```typescript
export type TaskType = "classification" | "vqa" | "detection" | "segmentation";
export type DatasetType = "image_classification" | "image_vqa" | "image_detection" | "image_segmentation";
```

**e. Create the shim component** `apps/web/src/views/datasets/shims/SegmentationDatasetsShim.vue` (copy `DetectionDatasetsShim.vue` as a template).

**f. Create the frontend schema module** `apps/web/src/views/datasets/schemas/image-segmentation.ts`:
```typescript
import { defineAsyncComponent } from "vue";
import { registerDatasetSchema } from "../schema-registry";

registerDatasetSchema({
  datasetType: "image_segmentation",
  taskType: "segmentation",
  annotationType: "masks",
  shimComponent: defineAsyncComponent(
    () => import("../shims/SegmentationDatasetsShim.vue"),
  ),
  mockSampleFactory: (index, labelSpace = ["object"]) => ({
    // same structure as _mock_item_generator in Python
  }),
});
```

**g. Register in the  add the import to `apps/web/src/views/datasets/registry.ts`:barrel**
```typescript
import "./schemas/image-segmentation";
```

#### Seed script (optional but recommended)

**h. Create** `libs/seedmaker/src/seedmaker/datasets/image_segmentation.py` using `SeedConfig` + `SeedRunner`:
```python
from seedmaker.config import SeedConfig
from seedmaker.runner import SeedRunner

config = SeedConfig(
    name="image-segmentation-mock",
    dataset_name="Segmentation Mock",
    dataset_type="image_segmentation",
    task_type="segmentation",
    label_space=["road", "sky", "car"],
)
```

**i. Register** in `libs/seedmaker/src/seedmaker/datasets/__init__.py`:
```python
from seedmaker.datasets import image_segmentation  # noqa: F401
```

### Annotation value for complex types

If your annotation type stores more than a string label (e.g., bounding boxes, masks, key-points), use the `annotation_value` JSON column:

- Set `label = ""` (kept non-null for backward compat).
- Set `annotation_value = [{ ... complex payload ... }]`.

The `CreateAnnotationRequest` already accepts `annotation_value: dict | list | None = None`.

### What you get automatically

After completing all steps above:
- `GET /api/v1/compatibility` will include your new pair.
- `POST /api/v1/datasets` will accept your new `dataset_type` + `task_type`.
- Label Studio projects will be created with the correct config.
- The preview feature will create datasets of the right type.
- The datasets list page will render your shim component.
- `SchemaAwareMockUpstream` will produce correctly-shaped preview items.

### Further reading

- [Dataset schema system](../architecture/dataset-schema-system.md)
- [Datasets shim architecture](../architecture/datasets-shim-architecture.md)
- `apps/api/app/domain/schemas/image_detection.py` — backend reference implementation
- `apps/web/src/views/datasets/schemas/image-detection.ts` — frontend reference implementation
