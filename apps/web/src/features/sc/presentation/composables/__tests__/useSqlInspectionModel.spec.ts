import { computed, effectScope, ref, type Ref } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  ScInvalidation,
  ScWorkbenchDataSource,
} from "@/features/sc/domain/workbenchDataSource";
import { createDefaultScSamplingProgram } from "@/features/sc/domain/samplingRules";
import type { ScLegendSource } from "@/features/sc/domain/workbenchInteraction";
import { useSqlInspectionModel } from "../useSqlInspectionModel";

function createDataSource() {
  let invalidationListener: ((event: ScInvalidation) => void) | null = null;
  const source: ScWorkbenchDataSource = {
    scopeKey: "dataset:ds-1",
    loadMap: vi.fn(async () => new Uint8Array([1, 2, 3])),
    loadRows: vi.fn(async () => ({ items: [], total: 0, nextAnchor: null })),
    loadGallery: vi.fn(async () => ({ ipc: null, total: 0, nextOffset: null })),
    loadAggregates: vi.fn(async () => ({ "1": 3 })),
    loadNumericRange: vi.fn(async () => ({ min: 1, max: 9 })),
    loadDistinctValues: vi.fn(async () => []),
    resolveSelection: vi.fn(async () => [3, 7]),
    subscribeInvalidations: vi.fn((listener) => {
      invalidationListener = listener;
      return () => {
        invalidationListener = null;
      };
    }),
    close: vi.fn(),
  };
  return {
    source,
    invalidate(event: ScInvalidation) {
      invalidationListener?.(event);
    },
  };
}

describe("useSqlInspectionModel", () => {
  const scopes: ReturnType<typeof effectScope>[] = [];

  afterEach(() => {
    for (const scope of scopes) scope.stop();
    scopes.length = 0;
  });

  function mount(
    source: ScWorkbenchDataSource,
    options: { legendGroupBy?: Ref<ScLegendSource | null | undefined> } = {},
  ) {
    const scope = effectScope();
    scopes.push(scope);
    return scope.run(() =>
      useSqlInspectionModel({
        dataSource: ref(source),
        legendGroupBy: computed(() => options.legendGroupBy?.value ?? "class"),
        globalFilter: computed(() => ({})),
        tableFilter: computed(() => ({})),
        tableSort: computed(() => null),
        reticle: computed(() => ({
          options: { xDieCount: 2, yDieCount: 2, xDieShift: 0, yDieShift: 0 },
          dieSizeX: 10,
          dieSizeY: 20,
        })),
        galleryRandomSamplingDefectIds: computed(() => undefined),
      }),
    );
  }

  it("keeps map and table selection in local workbench state", async () => {
    const { source } = createDataSource();
    const model = mount(source);
    if (!model) throw new Error("model was not created");
    await vi.waitFor(() => expect(source.loadMap).toHaveBeenCalled());
    vi.mocked(source.resolveSelection).mockClear();

    await model.applyMapSelection([9, 2, 9]);
    await model.appendMapSelection([7, 2]);
    model.setTableSelection({ kind: "ids", ids: ["sample-8", "sample-3", "sample-8"] });

    expect(model.mapSelectedDefectIds.value).toEqual([2, 7, 9]);
    expect(model.tableSelection.value).toEqual({
      kind: "ids",
      ids: ["sample-3", "sample-8"],
    });
    expect(model.galleryQuery.value.tableSelection).toEqual({
      kind: "ids",
      ids: ["sample-3", "sample-8"],
    });
    expect(source.resolveSelection).not.toHaveBeenCalled();
  });

  it("keeps select-all symbolic in the gallery query", () => {
    const { source } = createDataSource();
    const model = mount(source);
    if (!model) throw new Error("model was not created");

    model.setTableSelection({
      kind: "all",
      excludedIds: ["sample-9", "sample-3", "sample-9"],
    });

    expect(model.tableSelection.value).toEqual({
      kind: "all",
      excludedIds: ["sample-3", "sample-9"],
    });
    expect(model.galleryQuery.value.tableSelection).toEqual({
      kind: "all",
      excludedIds: ["sample-3", "sample-9"],
    });
  });

  it("can exclude the selected map defects from the table and gallery", async () => {
    const { source } = createDataSource();
    const model = mount(source);
    if (!model) throw new Error("model was not created");

    await model.applyMapSelection([9, 3, 9]);
    expect(model.galleryQuery.value.filters).toEqual([]);
    model.setMapSelectionMode("exclude");

    expect(model.mapSelectionMode.value).toBe("exclude");
    expect(model.canUndoMapSelectionMode.value).toBe(true);
    expect(model.galleryQuery.value.filters).toEqual([["defect_id", "not in", [3, 9]]]);
    expect(model.sampleTableDataSource.value?.scopeKey).toContain(
      JSON.stringify([["defect_id", "not in", [3, 9]]]),
    );

    await model.applyMapSelection([7]);
    expect(model.galleryQuery.value.filters).toEqual([["defect_id", "not in", [3, 9]]]);

    model.invertMapSelectionMode();
    expect(model.mapSelectionMode.value).toBe("include");
    expect(model.galleryQuery.value.filters).toEqual([["defect_id", "in", [3, 9]]]);
    model.undoMapSelectionMode();
    expect(model.mapSelectionMode.value).toBe("exclude");
    model.undoMapSelectionMode();
    expect(model.mapSelectionMode.value).toBeNull();
    expect(model.galleryQuery.value.filters).toEqual([]);
    expect(model.canUndoMapSelectionMode.value).toBe(false);

    model.setMapSelectionMode("include");
    expect(model.galleryQuery.value.filters).toEqual([["defect_id", "in", [7]]]);
  });

  it("reloads map queries when an SSE revision invalidates the scope", async () => {
    const { source, invalidate } = createDataSource();
    mount(source);
    await vi.waitFor(() => expect(source.loadMap).toHaveBeenCalledTimes(1));

    invalidate({ scope: "dataset:ds-1", revision: 2, changedKinds: ["prediction"] });

    await vi.waitFor(() => expect(source.loadMap).toHaveBeenCalledTimes(2));
  });

  it("publishes a legend column only with the Arrow snapshot loaded for it", async () => {
    const { source } = createDataSource();
    const legendGroupBy = ref<ScLegendSource>("class");
    let resolveRoughBin!: (value: Uint8Array) => void;
    vi.mocked(source.loadMap)
      .mockResolvedValueOnce(new Uint8Array([1]))
      .mockImplementationOnce(() => new Promise((resolve) => (resolveRoughBin = resolve)));
    const model = mount(source, { legendGroupBy });
    if (!model) throw new Error("model was not created");
    await vi.waitFor(() => expect(source.loadMap).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => expect(model.mapArrowData.value).not.toBeNull());
    expect(model.mapLegendColumn.value).toBe("class_number");

    legendGroupBy.value = "bin";
    await vi.waitFor(() => expect(source.loadMap).toHaveBeenCalledTimes(2));
    expect(model.mapLegendColumn.value).toBe("class_number");

    resolveRoughBin(new Uint8Array([2]));
    await vi.waitFor(() => expect(model.mapLegendColumn.value).toBe("rough_bin"));
    expect([...new Uint8Array(model.mapArrowData.value?.[0] ?? new ArrayBuffer())]).toEqual([2]);
  });

  it("reloads map and aggregates with the Review candidate filter", async () => {
    const { source } = createDataSource();
    const model = mount(source);
    if (!model) throw new Error("model was not created");
    await vi.waitFor(() => {
      expect(source.loadMap).toHaveBeenCalledTimes(1);
      expect(source.loadAggregates).toHaveBeenCalledTimes(1);
    });

    model.setReviewMode(true);

    await vi.waitFor(() => {
      expect(source.loadAggregates).toHaveBeenCalledTimes(2);
      expect(source.loadMap).toHaveBeenCalledTimes(2);
    });
    expect(source.loadMap).toHaveBeenLastCalledWith(
      expect.objectContaining({ filters: [["images", ">", 0]] }),
    );
  });

  it("uses Review, map selection, and seed for deterministic sampling", async () => {
    const { source } = createDataSource();
    const model = mount(source);
    if (!model) throw new Error("model was not created");
    await model.applyMapSelection([7, 3]);
    vi.mocked(source.resolveSelection).mockClear();

    const program = createDefaultScSamplingProgram();
    program.total.limit = 25;
    await model.querySamplingDefectIds(program, 1234, {
      reviewOnly: true,
      mapSelectionOnly: true,
      globalFilterEnabled: true,
    });

    expect(source.resolveSelection).toHaveBeenCalledWith(
      expect.objectContaining({
        filters: [
          ["images", ">", 0],
          ["defect_id", "in", [3, 7]],
        ],
        constraint: { kind: "sampling-program", program, seed: 1234 },
      }),
    );
  });

  it("can exclude the workbench Global Filter from a sampling program", async () => {
    const { source } = createDataSource();
    const scope = effectScope();
    scopes.push(scope);
    const model = scope.run(() =>
      useSqlInspectionModel({
        dataSource: ref(source),
        legendGroupBy: computed(() => "class" as const),
        globalFilter: computed(() => ({
          rough_bin: { filterType: "set" as const, values: [4] },
        })),
        tableFilter: computed(() => ({})),
        tableSort: computed(() => null),
        reticle: computed(() => ({
          options: { xDieCount: 2, yDieCount: 2, xDieShift: 0, yDieShift: 0 },
          dieSizeX: 10,
          dieSizeY: 20,
        })),
        galleryRandomSamplingDefectIds: computed(() => undefined),
      }),
    );
    if (!model) throw new Error("model was not created");
    vi.mocked(source.loadAggregates).mockClear();

    await model.querySamplingCandidateCount({
      reviewOnly: false,
      mapSelectionOnly: false,
      globalFilterEnabled: false,
    });

    expect(source.loadAggregates).toHaveBeenCalledWith(expect.objectContaining({ filters: [] }));
  });
});
