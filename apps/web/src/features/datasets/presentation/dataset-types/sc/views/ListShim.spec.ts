import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ListShim from "./ListShim.vue";
import type { DatasetListItem } from "@/shared/datasets/types";

const stubs = {
  DatasetToolbar: {
    template: "<div data-testid=\"toolbar\" />",
  },
  NButton: {
    template: "<button><slot /></button>",
  },
  NDataTable: {
    props: ["columns", "data"],
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

function makeDataset(datasetMeta: Record<string, unknown>): DatasetListItem {
  return {
    id: "dataset-1",
    name: "Patch A",
    dataset_type: "image_sc",
    task_spec: { task_type: "patch" },
    dataset_meta: datasetMeta,
    created_at: "2026-06-19T00:00:00Z",
  };
}

describe("SC dataset list shim", () => {
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

  it("shows sample counts from total_samples when sample_count is absent", () => {
    const wrapper = mount(ListShim, {
      props: {
        datasets: [makeDataset({ total_samples: 37 })],
        currentOrgId: "org-1",
        isSuperadmin: false,
      },
      global: { stubs },
    });

    expect(wrapper.text()).toContain("Samples");
    expect(wrapper.text()).toContain("37");
  });
});
