import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

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
});
