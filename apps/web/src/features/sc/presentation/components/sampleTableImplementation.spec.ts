import { describe, expect, it } from "vitest";
import { resolveScSampleTableImplementation } from "./sampleTableImplementation";

describe("resolveScSampleTableImplementation", () => {
  it("uses VXE unless the development comparison is explicitly requested", () => {
    expect(resolveScSampleTableImplementation("", true)).toBe("vxe");
    expect(resolveScSampleTableImplementation("?sc-table=vxe", true)).toBe("vxe");
    expect(resolveScSampleTableImplementation("?sc-table=tanstack", true)).toBe("tanstack");
  });

  it("does not expose the comparison renderer in a production build", () => {
    expect(resolveScSampleTableImplementation("?sc-table=tanstack", false)).toBe("vxe");
  });

  it("rejects an unknown explicit renderer", () => {
    expect(() => resolveScSampleTableImplementation("?sc-table=other", true)).toThrow(
      "Expected vxe or tanstack",
    );
  });
});
