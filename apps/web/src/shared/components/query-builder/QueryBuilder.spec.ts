import { describe, expect, it } from "vitest";
import { mountWithProviders } from "@/testing";
import QueryBuilder from "./QueryBuilder.vue";
import type { QueryBuilderGroup, QueryBuilderRule } from "./types";

interface TestRule {
  field: string;
}

function rule(id: string, field: string): QueryBuilderRule<TestRule> {
  return { kind: "rule", id, value: { field } };
}

describe("QueryBuilder", () => {
  it("edits the root combinator and adds a condition from the supplied factory", async () => {
    const model: QueryBuilderGroup<TestRule> = {
      kind: "group",
      id: "root",
      combinator: "and",
      items: [],
    };
    const { wrapper } = await mountWithProviders(QueryBuilder<TestRule>, {
      props: {
        modelValue: model,
        createRule: () => rule("created", "class_number"),
        root: true,
      },
      slots: {
        rule: ({ rule: queryRule }: { rule: QueryBuilderRule<TestRule> }) => queryRule.value.field,
      },
    });

    await wrapper.get('[data-testid="query-combinator-or"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")?.at(-1)?.[0]).toMatchObject({ combinator: "or" });

    await wrapper.get('[data-testid="query-add-condition"]').trigger("click");
    expect(wrapper.emitted("update:modelValue")?.at(-1)?.[0]).toMatchObject({
      items: [{ kind: "rule", id: "created", value: { field: "class_number" } }],
    });
  });

  it("updates a nested group without flattening its expression", async () => {
    const model: QueryBuilderGroup<TestRule> = {
      kind: "group",
      id: "root",
      combinator: "and",
      items: [
        {
          kind: "group",
          id: "classes",
          combinator: "and",
          items: [rule("class-two", "class_number"), rule("class-three", "class_number")],
        },
        rule("area", "area"),
      ],
    };
    const { wrapper } = await mountWithProviders(QueryBuilder<TestRule>, {
      props: {
        modelValue: model,
        createRule: () => rule("created", "rough_bin"),
        root: true,
      },
      slots: {
        rule: ({ rule: queryRule }: { rule: QueryBuilderRule<TestRule> }) => queryRule.value.field,
      },
    });

    expect(wrapper.findAll(".query-builder")).toHaveLength(2);
    expect(wrapper.text()).toContain("class_number");
    await wrapper.findAll('[data-testid="query-combinator-or"]')[1]!.trigger("click");

    expect(wrapper.emitted("update:modelValue")?.at(-1)?.[0]).toMatchObject({
      combinator: "and",
      items: [{ kind: "group", id: "classes", combinator: "or" }, { id: "area" }],
    });
  });
});
