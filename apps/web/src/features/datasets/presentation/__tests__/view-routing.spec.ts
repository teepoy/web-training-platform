import { describe, expect, it } from "vitest";

// Import route definitions
import { datasetRoutes } from "../../router";

// Import schema registry — trigger side-effect registrations
import "../dataset-types/classification/views/schema";
import {
  getDatasetSchema,
  getViewSchema,
  resolveDatasetShim,
  resolveViewComponent,
} from "../pages/schema-registry";

// ---------------------------------------------------------------------------
// Route structure — dataset detail no longer has a view child route
// ---------------------------------------------------------------------------

describe("view routing", () => {
  it("defines dataset detail route /datasets/:id without view child route", () => {
    const detailRoute = datasetRoutes.find((r) => r.path === "/datasets/:id");
    expect(detailRoute).toBeDefined();

    const children = detailRoute!.children ?? [];
    expect(children.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// View type resolution — GREEN: registry separates dataset type from view
// ---------------------------------------------------------------------------

describe("view type resolution", () => {
  it("resolves compatible view types for each dataset family", () => {
    const classifSchema = getDatasetSchema("image_classification");
    expect(classifSchema).toBeDefined();
    expect(classifSchema!.viewTypes).toBeDefined();
    expect(classifSchema!.viewTypes!.length).toBeGreaterThanOrEqual(2);
    expect(classifSchema!.viewTypes).toContain("image_input_v1");
    expect(classifSchema!.viewTypes).toContain("labeled_image_v1");
  });

  it("looks up schema by view type string via getViewSchema", () => {
    // Each viewType can be reverse-looked up to its parent schema descriptor
    // via the dedicated view registry (first-registration-wins for shared types).
    expect(getViewSchema("image_input_v1")).toBeDefined();
    expect(getViewSchema("labeled_image_v1")).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// labeled_image_v1 asymmetry — GREEN: dedicated rendering target exists
// ---------------------------------------------------------------------------

describe("labeled_image_v1 view type", () => {
  it("is registered in the schema registry", () => {
    const schema = getViewSchema("labeled_image_v1");
    expect(schema).toBeDefined();
    expect(schema!.datasetType).toBe("image_classification");
    expect(schema!.taskType).toBe("classification");
    expect(schema!.annotationType).toBe("choice");
  });

  it("has a resolvable rendering target distinct from the classification list shim", () => {
    // Classification list shim is the dataset list view
    const datasetListShim = resolveDatasetShim("image_classification");
    expect(datasetListShim).toBeDefined();

    // labeled_image_v1 should resolve to a DIFFERENT view rendering target
    // via the dedicated resolveViewComponent API.
    const labeledImageTarget = resolveViewComponent("labeled_image_v1");
    expect(labeledImageTarget).toBeDefined();
    expect(labeledImageTarget).not.toBe(datasetListShim);
  });

  it("is listed as a compatible view in the classification family schema", () => {
    const classifSchema = getDatasetSchema("image_classification");
    expect(classifSchema).toBeDefined();
    expect(classifSchema!.viewTypes).toContain("labeled_image_v1");
  });
});

// ---------------------------------------------------------------------------
// All families coverage — GREEN: selector handles every registered view
// ---------------------------------------------------------------------------

describe("view selector coverage", () => {
  const ALL_FAMILIES = [
    {
      datasetType: "image_classification" as const,
      compatibleViews: ["image_input_v1", "labeled_image_v1"],
    },
  ] as const;

  it("every registered dataset type declares compatible view types", () => {
    for (const family of ALL_FAMILIES) {
      const schema = getDatasetSchema(family.datasetType);
      expect(schema, `Schema for "${family.datasetType}" should be registered`).toBeDefined();

      for (const view of family.compatibleViews) {
        expect(
          schema!.viewTypes,
          `"${family.datasetType}" should list "${view}" as a compatible view`,
        ).toContain(view);
      }
    }
  });

  it("every compatible view type can be reverse-looked up to a parent schema", () => {
    // Each view type resolves to SOME parent schema via getViewSchema.
    // Shared view types (image_input_v1) use first-registration-wins and
    // map to the first family that registered them (classification).
    for (const family of ALL_FAMILIES) {
      for (const view of family.compatibleViews) {
        const schema = getViewSchema(view);
        expect(schema, `View type "${view}" should resolve to a parent schema`).toBeDefined();

        // For view types unique to a single family, verify exact parent match.
        // Shared types (image_input_v1) resolve to the first registered family.
        if (view !== "image_input_v1") {
          expect(
            schema!.datasetType,
            `View type "${view}" should resolve to "${family.datasetType}"`,
          ).toBe(family.datasetType);
        }
      }
    }
  });

  it("registry separates dataset type lookup from selected view rendering", () => {
    // Dataset type → list shim (via resolveDatasetShim)
    const classifList = resolveDatasetShim("image_classification");

    expect(classifList).toBeDefined();

    // View types → view rendering targets (via resolveViewComponent)
    // Each view type resolves to its own dedicated rendering component,
    // distinct from the dataset list shim.
    const labeledImageTarget = resolveViewComponent("labeled_image_v1");
    expect(labeledImageTarget).toBeDefined();
    expect(labeledImageTarget).not.toBe(classifList);
  });
});
