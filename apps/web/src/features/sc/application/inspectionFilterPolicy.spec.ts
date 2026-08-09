import { describe, expect, it } from "vitest";
import type { ScGlobalFilter } from "@/features/sc/domain/globalFilter";
import {
  applyMapSelectionToGlobalFilter,
  buildInspectionFilterPlan,
  buildSamplingCandidateFilters,
} from "./inspectionFilterPolicy";

function globalFilter(items: ScGlobalFilter["items"] = []): ScGlobalFilter {
  return { combinator: "and", items };
}

describe("SC inspection filter policy", () => {
  it("locks the G, G+T, and G+T+Y query scopes", () => {
    const plan = buildInspectionFilterPlan({
      globalFilter: globalFilter([
        {
          id: "rough-bin",
          field: "rough_bin",
          condition: { filterType: "set", values: [4] },
          source: { kind: "manual" },
        },
      ]),
      mapSelectionIds: [9, 3, 9],
      reviewMode: true,
      samplingIds: new Set(["11", "7"]),
    });

    const globalExpression = {
      combinator: "and",
      items: [["rough_bin", "in", [4]]],
    };
    expect(plan.mapFilters).toEqual([globalExpression]);
    expect(plan.aggregateFilters).toEqual(plan.mapFilters);
    expect(plan.selectionFilters).toEqual(plan.mapFilters);
    expect(plan.tableFilters).toEqual([
      globalExpression,
      ["map_id", "in", [3, 9]],
      ["map_id", "in", [7, 11]],
      ["images", ">", 0],
    ]);
    expect(plan.galleryBaseFilters).toEqual(plan.tableFilters);
  });

  it("appends independently removable map exclusions", () => {
    const first = applyMapSelectionToGlobalFilter(globalFilter(), [9, 3, 9], "exclude");
    const second = applyMapSelectionToGlobalFilter(first, [7, 3], "exclude");

    expect(second.items).toHaveLength(2);
    expect(second.items.map((item) => item.id)).toEqual([first.items[0]?.id, second.items[1]?.id]);
    expect(second.items.map((item) => ({ field: item.field, condition: item.condition }))).toEqual([
      {
        field: "map_id",
        condition: { filterType: "set", values: [3, 9], exclude: true },
      },
      {
        field: "map_id",
        condition: { filterType: "set", values: [3, 7], exclude: true },
      },
    ]);
  });

  it("keeps repeated properties as independent AND predicates", () => {
    const filter = globalFilter([
      {
        id: "first",
        field: "defect_id",
        condition: { filterType: "set", values: [1, 2, 3, 4] },
        source: { kind: "manual" },
      },
    ]);

    const next = applyMapSelectionToGlobalFilter(filter, [2, 4], "exclude");
    const plan = buildInspectionFilterPlan({
      globalFilter: next,
      mapSelectionIds: [],
      reviewMode: false,
      samplingIds: undefined,
    });

    expect(plan.globalFilters).toEqual([
      {
        combinator: "and",
        items: [
          ["defect_id", "in", [1, 2, 3, 4]],
          ["map_id", "not in or null", [2, 4]],
        ],
      },
    ]);
  });

  it("constrains an OR root when a map action is committed", () => {
    const filter: ScGlobalFilter = {
      combinator: "or",
      items: [
        {
          id: "class-two",
          field: "class_number",
          condition: { filterType: "set", values: [2] },
          source: { kind: "manual" },
        },
        {
          id: "class-three",
          field: "class_number",
          condition: { filterType: "set", values: [3] },
          source: { kind: "manual" },
        },
      ],
    };

    const next = applyMapSelectionToGlobalFilter(filter, [10, 11], "exclude");

    expect(next).toMatchObject({
      combinator: "and",
      items: [
        { kind: "group", combinator: "or", items: filter.items },
        {
          field: "map_id",
          condition: { filterType: "set", values: [10, 11], exclude: true },
        },
      ],
    });
  });

  it("keeps sampling candidate options independent from the active cohort", () => {
    expect(
      buildSamplingCandidateFilters({
        baseFilter: globalFilter([
          {
            id: "rough-bin",
            field: "rough_bin",
            condition: { filterType: "set", values: [4] },
            source: { kind: "manual" },
          },
        ]),
        mapSelectionIds: [3, 7],
        tableSelection: { kind: "ids", ids: ["11", "12"] },
        options: {
          scope: "map",
          extraFilterEnabled: true,
          extraFilter: globalFilter([
            {
              id: "excluded",
              field: "defect_id",
              condition: { filterType: "set", values: [8, 9], exclude: true },
              source: { kind: "manual" },
            },
          ]),
        },
      }),
    ).toEqual([
      {
        combinator: "and",
        items: [["rough_bin", "in", [4]]],
      },
      {
        combinator: "and",
        items: [["defect_id", "not in or null", [8, 9]]],
      },
      ["map_id", "in", [3, 7]],
    ]);
  });

  it("uses the current table selection as a mutually exclusive candidate scope", () => {
    expect(
      buildSamplingCandidateFilters({
        baseFilter: globalFilter([
          {
            id: "rough-bin",
            field: "rough_bin",
            condition: { filterType: "set", values: [4] },
            source: { kind: "manual" },
          },
        ]),
        mapSelectionIds: [3, 7],
        tableSelection: { kind: "ids", ids: ["12", "5"] },
        options: {
          scope: "table",
          extraFilterEnabled: false,
          extraFilter: globalFilter([]),
        },
      }),
    ).toEqual([
      {
        combinator: "and",
        items: [["rough_bin", "in", [4]]],
      },
      ["row_key", "in", ["12", "5"]],
    ]);
  });
});
