import { describe, expect, it } from "vitest";
import { orgScopedQueryKey } from "./queryKeys";

describe("orgScopedQueryKey", () => {
  it("isolates otherwise identical queries by organization", () => {
    const endpointKey = ["api", "v1", "datasets", { offset: 20, limit: 20 }] as const;

    expect(orgScopedQueryKey("org-a", endpointKey)).not.toEqual(
      orgScopedQueryKey("org-b", endpointKey),
    );
  });

  it("keeps pagination and filtering inputs in the key", () => {
    const firstPage = orgScopedQueryKey("org-a", [
      "api",
      "v1",
      "datasets",
      { offset: 0, limit: 20, label: "ok" },
    ]);
    const secondPage = orgScopedQueryKey("org-a", [
      "api",
      "v1",
      "datasets",
      { offset: 20, limit: 20, label: "ok" },
    ]);

    expect(firstPage).not.toEqual(secondPage);
  });
});
