import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useAuthStore } from "./store";

describe("auth store", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("does not treat a cached user without a token as authenticated", () => {
    localStorage.setItem(
      "auth_user",
      JSON.stringify({
        id: "user-1",
        email: "user@example.com",
        name: "User",
        is_active: true,
        is_superadmin: false,
      }),
    );

    const store = useAuthStore();

    expect(store.user?.id).toBe("user-1");
    expect(store.token).toBeNull();
    expect(store.isAuthenticated).toBe(false);
  });
});
