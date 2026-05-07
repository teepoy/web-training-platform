# Plugin Extension Guide

This document describes the current extension model for the web app and API.

## Frontend plugin layout

- Sidebar widgets: `apps/web/src/plugins/sidebar-*/index.ts`
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

## Sidebar widgets

Sidebar panel descriptors in `apps/web/src/components/classify/sidebarConfig.ts` now only define panel layout and props. Widget component resolution happens at runtime through:

- `pluginRegistry.getSidebarComponent(key)` in `apps/web/src/components/sample-browser/BrowserSidebar.vue`

To add a widget:

1. Create `apps/web/src/plugins/sidebar-my-widget/index.ts`
2. Export a named descriptor via `defineSidebarPlugin({...})`
3. Import and register it in `apps/web/src/plugins/index.ts`:
   ```ts
   import { myWidgetPlugin } from "./sidebar-my-widget";
   pluginRegistry.registerSidebarWidget(myWidgetPlugin);
   ```
4. Add panel entry in one of:
   - `defaultPanels`
   - `datasetPanels`
   - `previewPanels`

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

## MCP server plugin auto-discovery

MCP plugin modules are auto-discovered from `libs/mcp-server/finetune_mcp/plugins/` by:

- `libs/mcp-server/finetune_mcp/plugins/loader.py`

Each plugin module can export:

- `TOOLS: list[Tool]`
- `HANDLERS: dict[str, Callable[[dict[str, Any]], Any]]`

Loaded plugin tools are merged into MCP tool listing and dispatch in `libs/mcp-server/finetune_mcp/server.py`.
