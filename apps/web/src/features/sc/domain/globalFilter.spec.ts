import { describe, expect, it } from "vitest";
import { scGlobalFilterConditionCount, toScWorkflowSampleFilter } from "./globalFilter";
import type { ScGlobalFilter } from "./globalFilter";

describe("SC Global Filter", () => {
  it("serializes nested AND and OR groups without UI metadata", () => {
    const filter: ScGlobalFilter = {
      combinator: "and",
      items: [
        {
          kind: "group",
          id: "classes",
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
        },
        {
          id: "excluded",
          field: "defect_id",
          condition: { filterType: "set", values: [11], exclude: true },
          source: { kind: "map-selection", action: "exclude-selected" },
        },
      ],
    };

    expect(scGlobalFilterConditionCount(filter)).toBe(3);
    expect(toScWorkflowSampleFilter(filter)).toEqual({
      combinator: "and",
      items: [
        {
          kind: "group",
          combinator: "or",
          items: [
            {
              kind: "condition",
              field: "class_number",
              condition: { filterType: "set", values: [2] },
            },
            {
              kind: "condition",
              field: "class_number",
              condition: { filterType: "set", values: [3] },
            },
          ],
        },
        {
          kind: "condition",
          field: "defect_id",
          condition: { filterType: "set", values: [11], exclude: true },
        },
      ],
    });
  });

  it("omits empty groups from workflow transport", () => {
    const filter: ScGlobalFilter = {
      combinator: "or",
      items: [{ kind: "group", id: "empty", combinator: "and", items: [] }],
    };

    expect(scGlobalFilterConditionCount(filter)).toBe(0);
    expect(toScWorkflowSampleFilter(filter)).toBeNull();
  });

  it("omits empty set conditions from workflow transport", () => {
    const filter: ScGlobalFilter = {
      combinator: "and",
      items: [
        {
          id: "empty-set",
          field: "class_number",
          condition: { filterType: "set", values: [] },
          source: { kind: "manual" },
        },
      ],
    };

    expect(toScWorkflowSampleFilter(filter)).toBeNull();
  });
});
