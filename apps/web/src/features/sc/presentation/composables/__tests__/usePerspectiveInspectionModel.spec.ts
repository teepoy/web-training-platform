import type { Table, ViewConfigUpdate } from "@perspective-dev/client";
import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

const capturedViewConfigs = vi.hoisted(() => [] as Array<{ readonly value: ViewConfigUpdate }>);

vi.mock("@/features/sc/presentation/components/composables/useManagedPerspectiveView", async () => {
  const { ref: vueRef } = await import("vue");
  return {
    useManagedPerspectiveView: (_table: unknown, config: { readonly value: ViewConfigUpdate }) => {
      capturedViewConfigs.push(config);
      return {
        snapshot: vueRef(null),
        isPending: vueRef(false),
        errorMessage: vueRef(null),
        latestBuildTiming: vueRef(null),
      };
    },
  };
});

vi.mock("@/features/sc/presentation/components/composables/usePerspectiveMapView", async () => {
  const { ref: vueRef } = await import("vue");
  return {
    usePerspectiveMapView: () => ({
      arrowData: vueRef(null),
      pending: vueRef(false),
      error: vueRef(null),
      progressMessage: vueRef(""),
      progressPercent: vueRef(0),
    }),
  };
});

import { usePerspectiveInspectionModel } from "../usePerspectiveInspectionModel";

describe("usePerspectiveInspectionModel.highlightDefectsForIds", () => {
  beforeEach(() => {
    capturedViewConfigs.length = 0;
  });

  it("returns empty array when no table", async () => {
    const model = usePerspectiveInspectionModel({
      perspectiveTable: ref(null),
      legendGroupBy: ref("class"),
      tableFilter: ref({}),
      reticleExpressions: ref({ reticle_x: '"die_x"', reticle_y: '"die_y"' }),
    });
    const result = await model.highlightDefectsForIds([1, 2, 3]);
    expect(result).toEqual([]);
  });

  it("returns empty array when given empty ids", async () => {
    const model = usePerspectiveInspectionModel({
      perspectiveTable: ref(null),
      legendGroupBy: ref("class"),
      tableFilter: ref({}),
      reticleExpressions: ref({ reticle_x: '"die_x"', reticle_y: '"die_y"' }),
    });
    const result = await model.highlightDefectsForIds([]);
    expect(result).toEqual([]);
  });

  it("filters the gallery through table_in_selection for every selection size", async () => {
    let nextPort = 0;
    const update = vi.fn(async () => undefined);
    const table = {
      make_port: vi.fn(async () => {
        nextPort += 1;
        return nextPort;
      }),
      update,
    } as unknown as Table;
    const model = usePerspectiveInspectionModel({
      perspectiveTable: ref<Table | null>(table),
      legendGroupBy: ref("class"),
      tableFilter: ref({}),
      reticleExpressions: ref({ reticle_x: '"die_x"', reticle_y: '"die_y"' }),
    });

    await model.setTableSelectedDefectIds([7]);

    expect(update).toHaveBeenNthCalledWith(
      1,
      {
        defect_id: [7],
        table_in_selection: [1],
      },
      { port_id: 2, format: null },
    );
    const blinkConfig = capturedViewConfigs[0]?.value;
    expect(blinkConfig?.filter).toContainEqual(["table_in_selection", "==", 1]);
    expect(blinkConfig?.filter).not.toContainEqual(["defect_id", "in", [7]]);

    await model.setTableSelectedDefectIds([7, 8]);
    expect(update).toHaveBeenNthCalledWith(
      2,
      {
        defect_id: [8],
        table_in_selection: [1],
      },
      { port_id: 2, format: null },
    );

    await model.setTableSelectedDefectIds([8]);
    expect(update).toHaveBeenNthCalledWith(
      3,
      {
        defect_id: [7],
        table_in_selection: [0],
      },
      { port_id: 2, format: null },
    );
  });

  it("serializes rapid selection changes and applies the newest state as a delta", async () => {
    let releaseFirstUpdate: (() => void) | undefined;
    let updateCount = 0;
    const update = vi.fn(async () => {
      updateCount += 1;
      if (updateCount === 1) {
        await new Promise<void>((resolve) => {
          releaseFirstUpdate = resolve;
        });
      }
    });
    let nextPort = 0;
    const table = {
      make_port: vi.fn(async () => {
        nextPort += 1;
        return nextPort;
      }),
      update,
    } as unknown as Table;
    const model = usePerspectiveInspectionModel({
      perspectiveTable: ref<Table | null>(table),
      legendGroupBy: ref("class"),
      tableFilter: ref({}),
      reticleExpressions: ref({ reticle_x: '"die_x"', reticle_y: '"die_y"' }),
    });

    const selectAll = model.setTableSelectedDefectIds([1, 2, 3]);
    await vi.waitFor(() => {
      expect(update).toHaveBeenCalledTimes(1);
    });
    const deselectFirst = model.setTableSelectedDefectIds([2, 3]);
    await Promise.resolve();
    expect(update).toHaveBeenCalledTimes(1);

    releaseFirstUpdate?.();
    await Promise.all([selectAll, deselectFirst]);

    expect(update).toHaveBeenNthCalledWith(
      2,
      {
        defect_id: [1],
        table_in_selection: [0],
      },
      { port_id: 2, format: null },
    );
    expect(model.tableSelectedDefectIds.value).toEqual([2, 3]);
  });

  it("appends consecutive box selections and updates only newly added rows", async () => {
    let nextPort = 0;
    const update = vi.fn(async () => undefined);
    const table = {
      make_port: vi.fn(async () => {
        nextPort += 1;
        return nextPort;
      }),
      update,
    } as unknown as Table;
    const model = usePerspectiveInspectionModel({
      perspectiveTable: ref<Table | null>(table),
      legendGroupBy: ref("class"),
      tableFilter: ref({}),
      reticleExpressions: ref({ reticle_x: '"die_x"', reticle_y: '"die_y"' }),
    });

    const firstSelection = model.appendMapSelection([3, 1]);
    const secondSelection = model.appendMapSelection([3, 2]);

    await expect(firstSelection).resolves.toEqual([1, 3]);
    await expect(secondSelection).resolves.toEqual([1, 2, 3]);

    expect(update).toHaveBeenNthCalledWith(
      1,
      {
        defect_id: [1, 3],
        map_in_selection: [1, 1],
      },
      { port_id: 1, format: null },
    );
    expect(update).toHaveBeenNthCalledWith(
      2,
      {
        defect_id: [2],
        map_in_selection: [1],
      },
      { port_id: 1, format: null },
    );
    expect(model.mapSelectedDefectIds.value).toEqual([1, 2, 3]);
    // Table-selection updates do not affect the Sample Table view and may be
    // ignored. Map-selection updates change its filter result and must refresh.
    expect(model.sampleTableIgnoredUpdatePortIds.value).toEqual([2]);
  });
});
