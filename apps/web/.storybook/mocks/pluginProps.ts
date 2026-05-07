import { fn } from "@storybook/test";
import type {
  ImportPluginRequiredProps,
  ExportPluginRequiredProps,
  PreviewLauncherRequiredProps,
} from "@platform/plugin-sdk";

export function mockImportProps(
  overrides: Partial<ImportPluginRequiredProps> = {},
): ImportPluginRequiredProps {
  return {
    datasetId: "dataset-storybook-001",
    onComplete: fn(),
    onCancel: fn(),
    ...overrides,
  };
}

export function mockExportProps(
  overrides: Partial<ExportPluginRequiredProps> = {},
): ExportPluginRequiredProps {
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