import { computed, effectScope, ref, type Ref } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  ScInvalidation,
  ScWorkbenchDataSource,
} from "@/features/sc/domain/workbenchDataSource";
import { emptyScGlobalFilter, type ScGlobalFilter } from "@/features/sc/domain/globalFilter";
import { createDefaultScAnnotationSamplingProgram } from "@/features/sc/domain/samplingRules";
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
    options: {
      globalFilter?: ScGlobalFilter;
      samplingIds?: Ref<Set<string> | undefined>;
      legendGroupBy?: Ref<ScLegendSource | null | undefined>;
    } = {},
  ) {
    const scope = effectScope();
    scopes.push(scope);
    return scope.run(() =>
      useSqlInspectionModel({
        dataSource: ref(source),
        legendGroupBy: computed(() => options.legendGroupBy?.value ?? "class"),
        globalFilter: computed(() => options.globalFilter ?? emptyScGlobalFilter()),
        tableFilter: computed(() => ({})),
        tableSort: computed(() => null),
        reticle: computed(() => ({
          options: { xDieCount: 2, yDieCount: 2, xDieShift: 0, yDieShift: 0 },
          dieSizeX: 10,
          dieSizeY: 20,
        })),
        galleryRandomSamplingDefectIds: computed(() => options.samplingIds?.value),
      }),
    );
  }

  it("keeps map and table selection in local workbench state", async () => {
    const { source } = createDataSource();
    const model = mount(source);
    if (!model) throw new Error("model was not created");
    await vi.waitFor(() => expect(source.loadMap).toHaveBeenCalled());
    vi.mocked(source.resolveSelection).mockClear();

    model.applyMapSelection([9, 2, 7, 9]);
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

  it("filters table and gallery immediately from the transient map selection", async () => {
    const { source } = createDataSource();
    const model = mount(source);
    if (!model) throw new Error("model was not created");

    model.applyMapSelection([9, 3, 9]);
    expect(model.galleryQuery.value.filters).toEqual([["map_id", "in", [3, 9]]]);
    expect(model.sampleTableDataSource.value?.scopeKey).toContain(
      JSON.stringify([["map_id", "in", [3, 9]]]),
    );

    model.applyMapSelection([3, 7, 9]);
    expect(model.galleryQuery.value.filters).toEqual([["map_id", "in", [3, 7, 9]]]);

    model.clearMapSelection();
    expect(model.galleryQuery.value.filters).toEqual([]);
  });

  it("combines map selection with the workbench Global Filter", async () => {
    const { source } = createDataSource();
    const model = mount(source, {
      globalFilter: {
        combinator: "and",
        items: [
          {
            id: "rough-bin",
            field: "rough_bin",
            condition: { filterType: "set", values: [4] },
            source: { kind: "manual" },
          },
        ],
      },
    });
    if (!model) throw new Error("model was not created");

    model.applyMapSelection([9, 3]);

    expect(model.galleryQuery.value.filters).toEqual([
      { combinator: "and", items: [["rough_bin", "in", [4]]] },
      ["map_id", "in", [3, 9]],
    ]);
  });

  it("applies a committed map exclusion through every Global Filter consumer", async () => {
    const { source } = createDataSource();
    const model = mount(source, {
      globalFilter: {
        combinator: "and",
        items: [
          {
            id: "exclude-map",
            field: "defect_id",
            condition: { filterType: "set", values: [3, 9], exclude: true },
            source: { kind: "map-selection", action: "exclude-selected" },
          },
        ],
      },
    });
    if (!model) throw new Error("model was not created");
    const globalFilters = [
      {
        combinator: "and",
        items: [["defect_id", "not in or null", [3, 9]]],
      },
    ];

    await vi.waitFor(() => {
      expect(source.loadMap).toHaveBeenCalledWith(
        expect.objectContaining({ filters: globalFilters }),
      );
      expect(source.loadAggregates).toHaveBeenCalledWith(
        expect.objectContaining({ filters: globalFilters }),
      );
    });
    expect(model.galleryQuery.value.filters).toEqual(globalFilters);
    expect(model.sampleTableDataSource.value?.scopeKey).toContain(JSON.stringify(globalFilters));
  });

  it("excludes only the edited Global Filter item from numeric range lookup", async () => {
    const { source } = createDataSource();
    const model = mount(source, {
      globalFilter: {
        combinator: "and",
        items: [
          {
            id: "area-lower",
            field: "area",
            condition: { filterType: "number", type: "inRange", filter: 1, filterTo: 10 },
            source: { kind: "manual" },
          },
          {
            id: "area-upper",
            field: "area",
            condition: { filterType: "number", type: "inRange", filter: 3, filterTo: 8 },
            source: { kind: "manual" },
          },
        ],
      },
    });
    if (!model) throw new Error("model was not created");
    vi.mocked(source.loadNumericRange).mockClear();

    await model.loadGlobalNumericRange("area", "area-lower");

    expect(source.loadNumericRange).toHaveBeenCalledWith(
      expect.objectContaining({
        field: "area",
        filters: [
          {
            combinator: "and",
            items: [
              {
                combinator: "and",
                items: [
                  ["area", ">=", 3],
                  ["area", "<=", 8],
                ],
              },
            ],
          },
        ],
      }),
    );
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

  it("keeps Review filtering scoped to table and gallery", async () => {
    const { source } = createDataSource();
    const model = mount(source);
    if (!model) throw new Error("model was not created");
    await vi.waitFor(() => {
      expect(source.loadMap).toHaveBeenCalledTimes(1);
      expect(source.loadAggregates).toHaveBeenCalledTimes(1);
    });

    model.setReviewMode(true);

    expect(model.galleryQuery.value.filters).toEqual([["images", ">", 0]]);
    expect(model.sampleTableDataSource.value?.scopeKey).toContain(
      JSON.stringify([["images", ">", 0]]),
    );
    await Promise.resolve();
    expect(source.loadAggregates).toHaveBeenCalledTimes(1);
    expect(source.loadMap).toHaveBeenCalledTimes(1);
  });

  it("keeps random sampling scoped to table and gallery", async () => {
    const { source } = createDataSource();
    const samplingIds = ref<Set<string> | undefined>(undefined);
    const model = mount(source, { samplingIds });
    if (!model) throw new Error("model was not created");
    await vi.waitFor(() => {
      expect(source.loadMap).toHaveBeenCalledTimes(1);
      expect(source.loadAggregates).toHaveBeenCalledTimes(1);
    });

    samplingIds.value = new Set(["11", "7"]);

    expect(model.galleryQuery.value.filters).toEqual([["map_id", "in", [7, 11]]]);
    await Promise.resolve();
    expect(source.loadMap).toHaveBeenCalledTimes(1);
    expect(source.loadAggregates).toHaveBeenCalledTimes(1);
  });

  it("uses one candidate scope and the seed for deterministic sampling", async () => {
    const { source } = createDataSource();
    const model = mount(source);
    if (!model) throw new Error("model was not created");
    await model.applyMapSelection([7, 3]);
    vi.mocked(source.resolveSelection).mockClear();

    const program = createDefaultScAnnotationSamplingProgram();
    program.rules = [{ type: "random_count", count: 25 }];
    await model.querySamplingDefectIds(program, 1234, {
      scope: "map",
      extraFilterEnabled: true,
      extraFilter: { combinator: "and", items: [] },
    });

    expect(source.resolveSelection).toHaveBeenCalledWith(
      expect.objectContaining({
        filters: [["map_id", "in", [3, 7]]],
        constraint: { kind: "sampling-program", program, seed: 1234 },
      }),
    );
  });

  it("keeps the workbench filter when the sampling Extra filter is disabled", async () => {
    const { source } = createDataSource();
    const scope = effectScope();
    scopes.push(scope);
    const model = scope.run(() =>
      useSqlInspectionModel({
        dataSource: ref(source),
        legendGroupBy: computed(() => "class" as const),
        globalFilter: computed(() => ({
          combinator: "and" as const,
          items: [
            {
              id: "rough-bin",
              field: "rough_bin",
              condition: { filterType: "set" as const, values: [4] },
              source: { kind: "manual" as const },
            },
          ],
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
      scope: "all",
      extraFilterEnabled: false,
      extraFilter: { combinator: "and", items: [] },
    });

    expect(source.loadAggregates).toHaveBeenCalledWith(
      expect.objectContaining({
        filters: [{ combinator: "and", items: [["rough_bin", "in", [4]]] }],
      }),
    );
  });
});
