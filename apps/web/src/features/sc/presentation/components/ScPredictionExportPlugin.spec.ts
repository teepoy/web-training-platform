import { h } from "vue";
import { NMessageProvider } from "naive-ui";
import { flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { mountWithProviders } from "@/testing";
import ScPredictionExportPlugin from "./ScPredictionExportPlugin.vue";

const { streamApiSseMock } = vi.hoisted(() => ({ streamApiSseMock: vi.fn() }));

vi.mock("@/shared/api/sse", () => ({ streamApiSse: streamApiSseMock }));

describe("ScPredictionExportPlugin", () => {
  beforeEach(() => {
    streamApiSseMock.mockReset();
  });

  it("offers KLARF, Parquet, and ZIP with optional Annotation Sampling", async () => {
    const { wrapper } = await mountWithProviders(NMessageProvider, {
      slots: {
        default: () =>
          h(ScPredictionExportPlugin, {
            datasetId: "dataset-1",
            onComplete: vi.fn(),
            onCancel: vi.fn(),
            embedded: true,
          }),
      },
    });

    const formatButtons = wrapper.findAll('[role="radio"]');
    expect(formatButtons).toHaveLength(3);
    expect(wrapper.text()).toContain("Parquet");
    expect(wrapper.text()).toContain("KLARF");
    expect(wrapper.text()).toContain("ZIP package");
    expect(wrapper.text()).toContain("Defect images are optional");
    expect(wrapper.text()).toContain("Annotation Sampling");
    expect(wrapper.text()).toContain("Large exports may take several minutes");
    expect(wrapper.text()).toContain("byte-range resume support");
    expect(wrapper.text()).not.toContain("Close");
    expect(formatButtons[0]?.attributes("aria-checked")).toBe("true");
    expect(wrapper.text()).not.toContain("KLARF version");

    await formatButtons[1]?.trigger("click");
    expect(formatButtons[1]?.attributes("aria-checked")).toBe("true");
    expect(formatButtons[0]?.attributes("aria-checked")).toBe("false");
    expect(wrapper.text()).toContain("KLARF version");
    expect(wrapper.get('[aria-label="KLARF version 1.2"]').exists()).toBe(true);
    expect(wrapper.get('[aria-label="KLARF version 1.8"]').exists()).toBe(true);
    expect(wrapper.get('[aria-label="Include defect images"]').exists()).toBe(true);

    wrapper.unmount();
  });

  it("explains Collection selection and inspection-level KLARF packaging", async () => {
    const { wrapper } = await mountWithProviders(NMessageProvider, {
      slots: {
        default: () =>
          h(ScPredictionExportPlugin, {
            collectionId: "collection-1",
            memberIds: ["member-1", "member-2"],
            memberDatasetIds: ["dataset-1", "dataset-2"],
            onComplete: vi.fn(),
            onCancel: vi.fn(),
          }),
      },
    });

    expect(wrapper.text()).toContain("Parquet combines the selected Collection records");
    expect(wrapper.text()).toContain("complete numbered files");
    expect(wrapper.text()).toContain("does not split files by byte size");
    wrapper.unmount();
  });

  it("submits the selected KLARF version and defect-image choice", async () => {
    streamApiSseMock.mockResolvedValue({
      payload: {
        uri: "exports/dataset-1/predictions.zip",
        rows: 3,
        format: "klarf",
        filename: "predictions.zip",
        sampled: false,
        klarf_version: "1.8",
      },
    });
    const { wrapper } = await mountWithProviders(NMessageProvider, {
      slots: {
        default: () =>
          h(ScPredictionExportPlugin, {
            datasetId: "dataset-1",
            onComplete: vi.fn(),
            onCancel: vi.fn(),
            embedded: true,
          }),
      },
    });

    await wrapper.findAll('[role="radio"]')[1]?.trigger("click");
    await wrapper.get('[aria-label="KLARF version 1.8"]').trigger("click");
    await wrapper.get('[aria-label="Include defect images"]').trigger("click");
    await wrapper.get(".actions button").trigger("click");
    await flushPromises();

    expect(streamApiSseMock).toHaveBeenCalledWith(
      "/sc/datasets/dataset-1/prediction-exports/stream",
      expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({
          format: "klarf",
          klarf_version: "1.8",
          include_images: true,
        }),
      }),
    );
    expect(wrapper.text()).toContain("KLARF 1.8");
    wrapper.unmount();
  });
});
