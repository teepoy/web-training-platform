import { describe, expect, it, vi } from "vitest";
import { useScFilterLookupController } from "./useScFilterLookupController";

describe("useScFilterLookupController", () => {
  it("ignores stale distinct-value responses", async () => {
    const controller = useScFilterLookupController();
    let resolveFirst: ((values: string[]) => void) | undefined;
    const first = controller.searchDistinct(
      { field: "class_number", search: "1" },
      () => new Promise((resolve) => (resolveFirst = resolve)),
    );
    await controller.searchDistinct({ field: "class_number", search: "12" }, async () => ["12"]);
    resolveFirst?.(["1"]);
    await first;

    expect(controller.distinctValues.value.class_number).toEqual(["12"]);
  });

  it("tracks range loading and failure by rule key", async () => {
    const controller = useScFilterLookupController();
    const onError = vi.fn();
    await controller.requestRange(
      { field: "area", itemId: "area-rule" },
      async () => {
        throw new Error("unavailable");
      },
      { onError },
    );

    expect(controller.numericRangeLoading.value["area-rule"]).toBe(false);
    expect(controller.numericRangeErrors.value["area-rule"]).toBe(true);
    expect(onError).toHaveBeenCalledOnce();
  });
});
