import { describe, expect, it } from "vitest";
import { copyMapArrowChunksForTransfer } from "@platform/sc-map-element";

describe("SC map Arrow buffer ownership", () => {
  it("transfers disposable copies and leaves application buffers reusable", () => {
    const sources = [Uint8Array.from([1, 2, 3]).buffer, Uint8Array.from([4, 5]).buffer];

    const firstTransfer = copyMapArrowChunksForTransfer(sources);
    expect(firstTransfer[0]).not.toBe(sources[0]);
    expect([...new Uint8Array(firstTransfer[0])]).toEqual([1, 2, 3]);

    structuredClone(firstTransfer, { transfer: firstTransfer });
    expect(firstTransfer.map((chunk) => chunk.byteLength)).toEqual([0, 0]);
    expect(sources.map((chunk) => chunk.byteLength)).toEqual([3, 2]);

    const secondTransfer = copyMapArrowChunksForTransfer(sources);
    expect([...new Uint8Array(secondTransfer[0])]).toEqual([1, 2, 3]);
    expect([...new Uint8Array(secondTransfer[1])]).toEqual([4, 5]);
  });
});
