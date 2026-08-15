import { ref } from "vue";
import { describe, expect, it } from "vitest";
import { useDefaultCreatorFilter } from "./useDefaultCreatorFilter";

describe("useDefaultCreatorFilter", () => {
  it("waits for auth, defaults to the current user, and preserves an explicit clear", () => {
    const orgId = ref<string | null>("org-1");
    const userId = ref<string | null>(null);
    const { creatorFilter, isReady } = useDefaultCreatorFilter(orgId, userId);

    expect(isReady.value).toBe(false);
    expect(creatorFilter.value).toBeNull();

    userId.value = "user-1";
    expect(isReady.value).toBe(true);
    expect(creatorFilter.value).toBe("user-1");

    creatorFilter.value = null;
    expect(isReady.value).toBe(true);
    expect(creatorFilter.value).toBeNull();

    orgId.value = "org-2";
    expect(creatorFilter.value).toBe("user-1");
  });
});
