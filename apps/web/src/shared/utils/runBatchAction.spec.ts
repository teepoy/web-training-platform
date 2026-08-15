import { describe, expect, it, vi } from "vitest";

import { runBatchAction } from "./runBatchAction";

describe("runBatchAction", () => {
  it("continues after a failure and reports each outcome", async () => {
    const action = vi.fn(async (id: string) => {
      if (id === "blocked") throw new Error("in use");
    });

    const result = await runBatchAction(["first", "blocked", "last"], action);

    expect(action.mock.calls.map(([id]) => id)).toEqual(["first", "blocked", "last"]);
    expect(result.succeeded).toEqual(["first", "last"]);
    expect(result.failed).toHaveLength(1);
    expect(result.failed[0]?.item).toBe("blocked");
  });
});
