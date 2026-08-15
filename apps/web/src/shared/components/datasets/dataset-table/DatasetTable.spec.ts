import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import DatasetTable from "./DatasetTable.vue";
import type { DatasetListItem } from "../../../datasets/types";

describe("DatasetTable", () => {
  it("uses remote pagination for server-paged datasets", () => {
    const NDataTable = {
      props: ["remote"],
      template: "<div />",
    };
    const wrapper = mount(DatasetTable, {
      props: {
        datasets: [] as DatasetListItem[],
        columns: [],
        onRowClick: () => undefined,
        pagination: { page: 1, pageSize: 20, itemCount: 42 },
      },
      global: { stubs: { NDataTable } },
    });

    expect(wrapper.findComponent({ name: "DataTable" }).props("remote")).toBe(true);
  });

  it("adds controlled selection without turning checkbox clicks into row navigation", async () => {
    const onRowClick = vi.fn();
    const onUpdateCheckedRowKeys = vi.fn();
    const dataset = {
      id: "dataset-1",
      name: "Owned dataset",
      dataset_type: "image_classification",
      task_spec: {},
      created_at: "2026-01-01T00:00:00Z",
    } as DatasetListItem;
    const NDataTable = {
      name: "DataTable",
      props: ["columns", "rowProps", "checkedRowKeys"],
      emits: ["update:checked-row-keys"],
      template: "<div />",
    };
    const wrapper = mount(DatasetTable, {
      props: {
        datasets: [dataset],
        columns: [],
        onRowClick,
        checkedRowKeys: [],
        rowCheckable: () => true,
        onUpdateCheckedRowKeys,
      },
      global: { stubs: { NDataTable } },
    });
    const table = wrapper.findComponent({ name: "DataTable" });

    expect(table.props("columns")[0]).toMatchObject({ type: "selection" });
    await table.vm.$emit("update:checked-row-keys", ["dataset-1"]);
    expect(onUpdateCheckedRowKeys).toHaveBeenCalledWith(["dataset-1"]);

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    table
      .props("rowProps")(dataset)
      .onClick({ target: checkbox } as unknown as MouseEvent);
    expect(onRowClick).not.toHaveBeenCalled();
  });
});
