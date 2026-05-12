/**
 * Explicit widget/importer/exporter registration barrel.
 * Imported once in main.ts before app.mount().
 * To disable a registration, comment out or remove its registration line.
 */

import { widgetRegistry } from "../core/registry";

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
  blinkTablePlugin,
} from "@platform/web-ui";

import { manualImportPlugin } from "./import-manual";
import { importDatasetManualPlugin } from "./import-dataset-manual";
import { importParquetPlugin } from "./import-parquet";

import { previewExportPlugin } from "./export-preview";
import { persistExportPlugin } from "./export-persist";
import { exportParquetPlugin } from "./export-parquet";

import { upstreamPreviewPlugin } from "./preview-upstream";

widgetRegistry.registerWidget(annotationProgressPlugin);
widgetRegistry.registerWidget(labelDistributionPlugin);
widgetRegistry.registerWidget(echartsGenericPlugin);
widgetRegistry.registerWidget(markdownLogPlugin);
widgetRegistry.registerWidget(dataTablePlugin);
widgetRegistry.registerWidget(metricCardsPlugin);
widgetRegistry.registerWidget(sampleViewerPlugin);
widgetRegistry.registerWidget(predictionSummaryPlugin);
widgetRegistry.registerWidget(waferMapPlugin);
widgetRegistry.registerWidget(interactiveScatterPlugin);
widgetRegistry.registerWidget(browserSummaryPlugin);
widgetRegistry.registerWidget(blinkTablePlugin);

widgetRegistry.registerImporter(manualImportPlugin);
widgetRegistry.registerImporter(importDatasetManualPlugin);
widgetRegistry.registerImporter(importParquetPlugin);

widgetRegistry.registerExporter(previewExportPlugin);
widgetRegistry.registerExporter(persistExportPlugin);
widgetRegistry.registerExporter(exportParquetPlugin);

widgetRegistry.registerPreviewLauncher(upstreamPreviewPlugin);
