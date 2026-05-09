/**
 * Explicit plugin registration barrel.
 * Imported once in main.ts before app.mount().
 * To disable a plugin, comment out or remove its registration line.
 */

import { pluginRegistry } from "../core/registry";

import {
  annotationProgressPlugin,
  browserSummaryPlugin,
  dataTablePlugin,
  echartsGenericPlugin,
  interactiveScatterPlugin,
  labelDistributionPlugin,
  markdownLogPlugin,
  metricCardsPlugin,
  predictionSummaryPlugin,
  sampleViewerPlugin,
  waferMapPlugin,
} from "@platform/web-ui";

import { manualImportPlugin } from "./import-manual";
import { importDatasetManualPlugin } from "./import-dataset-manual";
import { importParquetPlugin } from "./import-parquet";

import { previewExportPlugin } from "./export-preview";
import { persistExportPlugin } from "./export-persist";
import { exportParquetPlugin } from "./export-parquet";

import { upstreamPreviewPlugin } from "./preview-upstream";

pluginRegistry.registerSidebarWidget(annotationProgressPlugin);
pluginRegistry.registerSidebarWidget(labelDistributionPlugin);
pluginRegistry.registerSidebarWidget(echartsGenericPlugin);
pluginRegistry.registerSidebarWidget(markdownLogPlugin);
pluginRegistry.registerSidebarWidget(dataTablePlugin);
pluginRegistry.registerSidebarWidget(metricCardsPlugin);
pluginRegistry.registerSidebarWidget(sampleViewerPlugin);
pluginRegistry.registerSidebarWidget(predictionSummaryPlugin);
pluginRegistry.registerSidebarWidget(waferMapPlugin);
pluginRegistry.registerSidebarWidget(interactiveScatterPlugin);
pluginRegistry.registerSidebarWidget(browserSummaryPlugin);

pluginRegistry.registerImporter(manualImportPlugin);
pluginRegistry.registerImporter(importDatasetManualPlugin);
pluginRegistry.registerImporter(importParquetPlugin);

pluginRegistry.registerExporter(previewExportPlugin);
pluginRegistry.registerExporter(persistExportPlugin);
pluginRegistry.registerExporter(exportParquetPlugin);

pluginRegistry.registerPreviewLauncher(upstreamPreviewPlugin);
