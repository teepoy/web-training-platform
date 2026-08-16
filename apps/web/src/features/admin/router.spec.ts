import { defineComponent } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { describe, expect, it } from "vitest";
import { adminRoutes } from "./router";

const AdminShell = defineComponent({ template: "<router-view />" });

describe("Admin routes", () => {
  it("registers the infrastructure page below the protected Admin shell", () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/admin", component: AdminShell, children: adminRoutes }],
    });

    const resolved = router.resolve("/admin/infrastructure");

    expect(resolved.matched).toHaveLength(2);
    expect(resolved.matched[1]?.path).toBe("/admin/infrastructure");
  });
});
