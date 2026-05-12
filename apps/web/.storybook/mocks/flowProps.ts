import { fn } from "@storybook/test";
import type {
  ImporterProps,
  ExporterProps,
  PreviewLauncherRequiredProps,
} from "@platform/widget-sdk";

export function mockImportProps(
  overrides: Partial<ImporterProps> = {},
): ImporterProps {
  return {
    datasetId: "dataset-storybook-001",
    onComplete: fn(),
    onCancel: fn(),
    ...overrides,
  };
}

export function mockExportProps(
  overrides: Partial<ExporterProps> = {},
): ExporterProps {
  return {
    datasetId: "dataset-storybook-001",
    onComplete: fn(),
    onCancel: fn(),
    ...overrides,
  };
}

export function mockPreviewProps(
  overrides: Partial<PreviewLauncherRequiredProps> = {},
): PreviewLauncherRequiredProps {
  return {
    onComplete: fn(),
    onCancel: fn(),
    ...overrides,
  };
}
