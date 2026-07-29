import { tableFromArrays, tableToIPC } from "apache-arrow";
import { describe, expect, it } from "vitest";
import { ArrowBackedRows } from "./arrowBackedRows";
import { decodeSampleArrowIpc } from "./sampleArrowDecode";

function decoded(columns: Record<string, Array<number | string>>) {
  const ipc = tableToIPC(tableFromArrays(columns));
  const buffer = ipc.buffer.slice(ipc.byteOffset, ipc.byteOffset + ipc.byteLength) as ArrayBuffer;
  return decodeSampleArrowIpc(buffer);
}

describe("ArrowBackedRows", () => {
  it("uses the full defect id vector to size the virtual scroller without eager rows", () => {
    const store = new ArrowBackedRows();

    store.reset(4, decoded({ defect_id: [101, 102, 103, 104] }));

    expect(store.rows).toHaveLength(4);
    expect(store.rows.slice(0)).toBe(store.rows);
    expect(store.getStats()).toEqual({
      length: 4,
      hydratedRows: 0,
      rowObjectsCreated: 0,
    });
    expect(store.rows[3].defect_id).toBe("104");
    expect(store.rows[3]._isHydrated).toBe(false);
  });

  it("reads all numeric defect ids without creating virtual row objects", () => {
    const store = new ArrowBackedRows();

    store.reset(4, decoded({ defect_id: [101, 102, 103, 104] }));

    expect(store.getAllDefectIds()).toEqual([101, 102, 103, 104]);
    expect(store.getStats()).toEqual({
      length: 4,
      hydratedRows: 0,
      rowObjectsCreated: 0,
    });
  });

  it("reads hydrated fields from Arrow pages while preserving row identity", () => {
    const store = new ArrowBackedRows();
    store.reset(4, decoded({ defect_id: [101, 102, 103, 104] }));

    const rows = store.hydrate(
      2,
      decoded({
        defect_id: [103, 104],
        class_number: [7, 8],
        kill_ratio: [0.25, 0.5],
      }),
    );

    expect(rows[0]).toBe(store.rows[2]);
    expect(store.rows[2].defect_id).toBe("103");
    expect(store.rows[2].class_number).toBe(7);
    expect(store.rows[2].kill_ratio).toBe(0.25);
    expect(store.rows[2]._isHydrated).toBe(true);
    expect(store.rows[1].class_number).toBeUndefined();
    expect(store.getStats()).toEqual({
      length: 4,
      hydratedRows: 2,
      rowObjectsCreated: 3,
    });
  });

  it("evicts row objects and page tables outside the active scroll window", () => {
    const store = new ArrowBackedRows();
    store.reset(6, decoded({ defect_id: [101, 102, 103, 104, 105, 106] }));
    store.hydrate(0, decoded({ defect_id: [101, 102], class_number: [1, 2] }));
    store.hydrate(4, decoded({ defect_id: [105, 106], class_number: [5, 6] }));

    store.retainRange(4, 6);

    expect(store.getStats()).toEqual({
      length: 6,
      hydratedRows: 2,
      rowObjectsCreated: 2,
    });
    expect(store.rows[4].class_number).toBe(5);
  });
});
