import type { Router } from "vue-router";
import { sandboxRoutes } from "./sandbox/router";

/** Register development-only routes before Vue Router performs its first navigation. */
export function registerDevelopmentRoutes(router: Router): void {
  for (const route of sandboxRoutes) {
    router.addRoute(route);
  }
}
