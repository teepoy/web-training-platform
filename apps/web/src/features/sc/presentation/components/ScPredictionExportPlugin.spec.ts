import { h } from "vue";
import { NMessageProvider } from "naive-ui";
import { flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { mountWithProviders } from "@/testing";
import ScPredictionExportPlugin from "./ScPredictionExportPlugin.vue";

const { streamApiSseMock, loadAggregatesMock } = vi.hoisted(() => ({
  streamApiSseMock: vi.fn(),
  loadAggregatesMock: vi.fn(),
}));

vi.mock("@/shared/api/sse", () => ({ streamApiSse: streamApiSseMock }));
vi.mock("@/features/sc/api/sqlWorkbenchDataSource", () => ({
  SqlWorkbenchDataSource: class {
    loadAggregates = loadAggregatesMock;
    loadColumns = vi.fn().mockResolvedValue([
      {
        name: "rough_bin",
        arrowType: "Int64",
        nullable: false,
        presentation: {
          title: "Rough Bin",
          width: 120,
          filter: "set",
          visibility: "default",
          format: "plain",
          order: 1,
        },
      },
    ]);
    loadDistinctValues = vi.fn().mockResolvedValue([]);
    loadNumericRange = vi.fn().mockResolvedValue(null);
    close = vi.fn();
  },
}));

describe("ScPredictionExportPlugin", () => {
  beforeEach(() => {
    streamApiSseMock.mockReset();
    loadAggregatesMock.mockReset();
    loadAggregatesMock.mockImplementation(({ field }: { field: string }) =>
      Promise.resolve(
        field === "annotation_label"
          ? { "60": 4, __unlabeled__: 3 }
          : field === "prediction_label"
            ? { "40": 5, "60": 2 }
            : { "40": 3, "60": 4 },
      ),
    );
  });

  it("offers result-source distribution, formats, and Review Sampling with Extra Filter", async () => {
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

    const formatButtons = wrapper.findAll('.format-grid [role="radio"]');
    expect(formatButtons).toHaveLength(3);
    expect(wrapper.text()).toContain("Parquet");
    expect(wrapper.text()).toContain("KLARF");
    expect(wrapper.text()).toContain("ZIP package");
    expect(wrapper.get('[aria-label="Export Annotation results"]').exists()).toBe(true);
    expect(wrapper.get('[aria-label="Export Prediction results"]').exists()).toBe(true);
    expect(wrapper.get('[aria-label="Export Final Class results"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("Final Class distribution");
    expect(wrapper.text()).toContain("Review Sampling");
    expect(wrapper.text()).not.toContain("byte-range resume support");
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

    await wrapper.get('[aria-label="Export Annotation results"]').trigger("click");
    await wrapper.get(".sampling-card button").trigger("click");
    await flushPromises();
    expect(document.body.textContent).toContain("Extra filter");
    expect(loadAggregatesMock).toHaveBeenCalledWith({
      field: "wafer_key",
      filters: [["annotation_label", "not in and not null", ["", "0"]]],
    });

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

    expect(wrapper.text()).toContain("Selected Collection records are combined");
    expect(wrapper.text()).toContain("KLARF remains grouped by inspection");
    wrapper.unmount();
  });

  it("submits the selected result source, KLARF version, and defect-image choice", async () => {
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

    await wrapper.findAll('.format-grid [role="radio"]')[1]?.trigger("click");
    await wrapper.get('[aria-label="Export Annotation results"]').trigger("click");
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
          result_source: "annotation",
          klarf_version: "1.8",
          include_images: true,
        }),
      }),
    );
    expect(wrapper.text()).toContain("KLARF 1.8");
    wrapper.unmount();
  });
});
