import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ListShim from "./ListShim.vue";
import type { DatasetListItem } from "@/shared/datasets/types";

const stubs = {
  DatasetToolbar: {
    template: '<div data-testid="toolbar" />',
  },
  NButton: {
    template: "<button><slot /></button>",
  },
  NInput: {
    props: ["value"],
    emits: ["update:value"],
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
  },
  NSelect: {
    props: ["value", "options"],
    emits: ["update:value"],
    template: "<select :value=\"value ?? ''\"><slot /></select>",
  },
  NDataTable: {
    props: ["columns", "data", "remote"],
    template: `
      <table>
        <thead>
          <tr>
            <th v-for="column in columns" :key="column.key">{{ column.title }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in data" :key="row.id">
            <td v-for="column in columns" :key="column.key">
              <component v-if="column.render" :is="column.render(row)" />
              <span v-else>{{ row[column.key] }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    `,
  },
  NTag: {
    template: "<span><slot /></span>",
  },
  NText: {
    template: "<span><slot /></span>",
  },
};

function makeDataset(
  datasetMeta: Record<string, unknown>,
  overrides: Partial<DatasetListItem> = {},
): DatasetListItem {
  return {
    id: "dataset-1",
    name: "Patch A",
    dataset_type: "image_sc",
    task_spec: { task_type: "patch" },
    dataset_meta: datasetMeta,
    created_at: "2026-06-19T00:00:00Z",
    ...overrides,
  };
}

describe("SC dataset list shim", () => {
  it("uses remote pagination for server-paged rows", () => {
    const wrapper = mount(ListShim, {
      props: {
        datasets: [makeDataset({ total_samples: 12 })],
        currentOrgId: "org-1",
        isSuperadmin: false,
        pagination: { page: 1, pageSize: 20, itemCount: 42 },
      },
      global: { stubs },
    });

    expect(wrapper.findComponent({ name: "DataTable" }).props("remote")).toBe(true);
  });

  it("does not show the inspection workspace alert or inspection time column", () => {
    const wrapper = mount(ListShim, {
      props: {
        datasets: [makeDataset({ inspection_time: "2026-05-26T08:00:00Z", total_samples: 12 })],
        currentOrgId: "org-1",
        isSuperadmin: false,
      },
      global: { stubs },
    });

    expect(wrapper.text()).not.toContain("Patch inspection workspace");
    expect(wrapper.text()).not.toContain("Inspection Time");
    expect(wrapper.text()).not.toContain("2026-05-26T08:00:00Z");
  });

  it("does not show sample counts in the dataset list", () => {
    const wrapper = mount(ListShim, {
      props: {
        datasets: [makeDataset({ total_samples: 37 })],
        currentOrgId: "org-1",
        isSuperadmin: false,
      },
      global: { stubs },
    });

    expect(wrapper.text()).not.toContain("Samples");
    expect(wrapper.text()).not.toContain("37");
  });

  it("shows creator names and filters by keyword", async () => {
    const wrapper = mount(ListShim, {
      props: {
        datasets: [
          makeDataset(
            { total_samples: 37 },
            { id: "dataset-1", name: "Patch Alpha", creator_name: "Alice" },
          ),
          makeDataset(
            { total_samples: 11 },
            { id: "dataset-2", name: "Patch Beta", creator_name: "Bob" },
          ),
        ],
        currentOrgId: "org-1",
        isSuperadmin: false,
      },
      global: { stubs },
    });

    expect(wrapper.text()).toContain("Creator");
    expect(wrapper.text()).toContain("Alice");
    expect(wrapper.text()).toContain("Bob");

    await wrapper.find("input").setValue("alpha");

    expect(wrapper.text()).toContain("Patch Alpha");
    expect(wrapper.text()).not.toContain("Patch Beta");
  });
});
