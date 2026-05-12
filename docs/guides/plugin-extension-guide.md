# Plugin Extension Guide

This document describes the current extension model for the web app and API.

## Frontend plugin layout

- Widget implementation (.vue) files: `libs/web-ui/src/components/<name>/<Name>Widget.vue` — general-purpose shared components, not sidebar-specific
- Thin plugin descriptor wrappers: `libs/web-ui/src/plugins/sidebar-<name>/index.ts` — import the .vue from `components/<name>/` and export a `defineSidebarPlugin()` descriptor
- App-specific sidebar widgets: `apps/web/src/plugins/sidebar-*/index.ts` — same thin-wrapper pattern but app-scoped
- Importers: `apps/web/src/plugins/import-*/index.ts`
- Exporters: `apps/web/src/plugins/export-*/index.ts`
- Preview launchers: `apps/web/src/plugins/preview-*/index.ts`
- Registry singleton: `apps/web/src/core/registry.ts`
- Registration barrel (loaded before mount): `apps/web/src/plugins/index.ts`

Each plugin directory exports a named descriptor using SDK helpers:

- `defineSidebarPlugin`
- `defineImportPlugin`
- `defineExportPlugin`
- `definePreviewPlugin`
- `defineAgentSkill`

Descriptors are imported and registered in `apps/web/src/plugins/index.ts`.
Plugins do **not** self-register via side effects — they export descriptors,
and the barrel file calls `pluginRegistry.register*()` explicitly.

SDK package: `libs/plugin-sdk/`.
Shared UI and first-party sidebar widgets package: `libs/web-ui/`.

## Sidebar widgets (now page-level panels)

Sidebar panel descriptors in `apps/web/src/components/classify/sidebarConfig.ts` define panel layout and props. Widget component resolution happens at runtime through:

- `pluginRegistry.getSidebarComponent(key)` passed as the resolver prop to `@platform/web-ui`'s shared `BrowserSidebar.vue`
- `PanelHost` (`libs/web-ui/src/components/panel-host/PanelHost.vue`) can render the same `SidebarPanelDescriptor[]` in any page region — a toolbar, a drawer, or a standalone container — without a sidebar shell

### Widgets are not sidebar-only

Since Task 12 (taxonomy reorganization), widget .vue components live in `libs/web-ui/src/components/<name>/`, not inside `plugins/sidebar-<name>/`. This is intentional: widget components are general-purpose shared UI and can be imported directly by other components, rendered via `PanelHost` anywhere, or registered as sidebar plugins — all from the same source file.

The `plugins/sidebar-<name>/index.ts` directories are now thin plugin descriptors only. They import the component from `components/<name>/` and export a `defineSidebarPlugin()` wrapper for the registry-based resolution path.

### Page-level provider model

Pages that need widgets both inside and outside the sidebar call `usePagePanels()` (from `@platform/web-ui`) in `<script setup>`. This composable provides `BROWSER_DASHBOARD_KEY` and `SIDEBAR_WIDGET_INTERACTION_KEY` at the page root, so any widget anywhere in the component tree can inject the same dashboard context and interaction state. See `.sisyphus/notepads/sidebar-layout-decoupling/page-provider-contract.md` for the full contract.

To add a widget:

1. Create the .vue component in `libs/web-ui/src/components/<name>/<Name>Widget.vue` for reusable widgets, or `apps/web/src/components/<name>/<Name>Widget.vue` for app-specific widgets.
2. Create a thin plugin descriptor in `libs/web-ui/src/plugins/sidebar-<name>/index.ts` (reusable) or `apps/web/src/plugins/sidebar-<name>/index.ts` (app-specific), importing the .vue from `components/<name>/` and exporting a named descriptor via `defineSidebarPlugin({...})`.
3. For reusable widgets, export the descriptor from `libs/web-ui/src/index.ts` and the default component export.
4. Import and register the descriptor in `apps/web/src/plugins/index.ts`:
   ```ts
   import { myWidgetPlugin } from "@platform/web-ui";
   pluginRegistry.registerSidebarWidget(myWidgetPlugin);
   ```
5. Add panel entry in one of `defaultPanels`, `datasetPanels`, or `previewPanels` in `sidebarConfig.ts`.
6. (Optional) Use `<PanelHost :panels="myPanels" :componentResolver="..." />` anywhere in a page to render the same widget descriptors outside a sidebar — for example in a bottom panel or a floating toolbar. Pass `:context` and `:interaction` from `usePagePanels()` so widgets share the same reactive state.

## Import plugins (Dataset view)

Dataset import UI is plugin-driven using a 2-step flow via `PluginFlowModal`:

- Step 1: `PluginTypeSelector` shows available importers as selectable cards
- Step 2: Selected importer component is mounted inside the modal

Importers are discovered with `pluginRegistry.getImporters("dataset")`.

- `DatasetsView.vue` uses `PluginFlowModal` with `kind="import"` for dataset-creation importers (surface: `"dataset"`)
- `DatasetDetailView.vue` uses `PluginFlowModal` with `kind="import"` for sample-level importers (surface: `"dataset"`)

Plugin receives `ImportPluginRequiredProps`:
  - `datasetId`
  - `onComplete`
  - `onCancel`

Examples:

- `apps/web/src/plugins/import-manual/` — single-sample manual entry (surface: `"dataset"`)
- `apps/web/src/plugins/import-dataset-manual/` — JSON bulk import creating a new dataset (surface: `"dataset"`)

## Export plugins (Dataset view)

Dataset export UI is plugin-driven using a 2-step flow via `PluginFlowModal`:

- Step 1: `PluginTypeSelector` shows available exporters as selectable cards
- Step 2: Selected exporter component is mounted inside the modal

Exporters are discovered with `pluginRegistry.getExporters("dataset")`.

Plugin receives `ExportPluginRequiredProps`:
  - `datasetId`
  - `onComplete`
  - `onCancel`

Examples:

- `apps/web/src/plugins/export-preview/`
- `apps/web/src/plugins/export-persist/`

## Preview launcher plugins (Preview Dataset)

Preview creation is plugin-driven using a 2-step flow in `PreviewLaunchView.vue`:

- Step 1: `PluginTypeSelector` shows available preview launchers as selectable cards
- Step 2: Selected launcher component renders inline

Launchers are discovered with `pluginRegistry.getPreviewLaunchers("preview")` or `getPreviewLaunchers("dataset-list")`.

Plugin receives `PreviewLauncherRequiredProps`:
  - `onComplete(result: { sessionId: string })`
  - `onCancel`

On `onComplete`, the host navigates to `/preview/:sessionId`.

Example: `apps/web/src/plugins/preview-upstream/`

## Backend API plugin routes

API plugin routers are explicitly registered in:

- `apps/api/app/plugins/registry.py`

To add a new backend plugin route:

1. Create `apps/api/app/plugins/<name>/router.py` with an `APIRouter` named `router`
2. Import it in `apps/api/app/plugins/registry.py` and add it to `PLUGIN_ROUTERS`

There are currently no built-in backend plugin routes. Existing import and
export plugins use the typed frontend API client against core API endpoints.
