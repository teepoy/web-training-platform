import { describe, expect, it } from "vitest";
import type { RouteLocationNormalized } from "vue-router";
import { datasetCollectionRoutes } from "@/features/dataset-collections/router";
import { datasetRoutes } from "@/features/datasets/router";
import { libraryRoutes } from "./router";

function resolveRedirect(path: string, query: Record<string, string>) {
  const route = [...datasetRoutes, ...datasetCollectionRoutes].find(
    (candidate) => candidate.path === path,
  );
  expect(route).toBeDefined();
  expect(typeof route?.redirect).toBe("function");
  return (route?.redirect as (to: RouteLocationNormalized) => unknown)({
    query,
  } as RouteLocationNormalized);
}

describe("Library routes", () => {
  it("defines /library as the canonical workspace", () => {
    expect(libraryRoutes.find((route) => route.path === "/library")).toMatchObject({
      name: "library",
    });
  });

  it("redirects only the Dataset list route and preserves its shared query", () => {
    expect(resolveRedirect("/datasets", { q: "flowers", creator: "me" })).toEqual({
      path: "/library",
      query: { q: "flowers", creator: "me", tab: "datasets" },
    });
    expect(datasetRoutes.find((route) => route.path === "/datasets/:id")?.redirect).toBeUndefined();
  });

  it("redirects only the Collection list route and preserves its shared query", () => {
    expect(resolveRedirect("/dataset-collections", { q: "review" })).toEqual({
      path: "/library",
      query: { q: "review", tab: "collections" },
    });
    expect(
      datasetCollectionRoutes.find((route) => route.path === "/dataset-collections/:collectionId")
        ?.redirect,
    ).toBeUndefined();
  });
});
