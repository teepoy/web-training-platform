/**
 * Explicit plugin registration barrel.
 * Imported once in main.ts before app.mount().
 * To disable a plugin, comment out or remove its registration line.
 */

import { pluginRegistry } from "../core/registry";

import { annotationProgressPlugin } from "./sidebar-annotation-progress";
import { labelDistributionPlugin } from "./sidebar-label-distribution";
import { echartsGenericPlugin } from "./sidebar-echarts-generic";
import { markdownLogPlugin } from "./sidebar-markdown-log";
import { dataTablePlugin } from "./sidebar-data-table";
import { metricCardsPlugin } from "./sidebar-metric-cards";
import { sampleViewerPlugin } from "./sidebar-sample-viewer";
import { predictionSummaryPlugin } from "./sidebar-prediction-summary";
import { waferMapPlugin } from "./sidebar-wafer-map";
import { interactiveScatterPlugin } from "./sidebar-interactive-scatter";
import { browserSummaryPlugin } from "./sidebar-browser-summary";

import { manualImportPlugin } from "./import-manual";

import { previewExportPlugin } from "./export-preview";
import { persistExportPlugin } from "./export-persist";

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

pluginRegistry.registerExporter(previewExportPlugin);
pluginRegistry.registerExporter(persistExportPlugin);