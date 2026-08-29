import type { Meta, StoryObj } from "@storybook/vue3";
import { computed, ref } from "vue";
import { NButton, NCard, NCode, NSpace, NTag, NText } from "naive-ui";
import {
  cloneScGlobalFilter,
  emptyScGlobalFilter,
  type ScGlobalFilter,
} from "@/features/sc/domain/globalFilter";
import GlobalFilterModal from "./GlobalFilterModal.vue";

const optionSource: Record<string, Array<string | number>> = {
  test_id: ["TEST-001", "TEST-002", "TEST-ALPHA"],
  class_number: [0, 1, 2, 3, 10, 20],
  rough_bin: [0, 1, 2, 4, 8],
  final_bin: [0, 1, 2, 3],
  manual_bin: [0, 10, 20, 30],
  adder: ["false", "true"],
  cluster_id: [0, 1, 2, 12, 24],
  annotation_label: ["Clean", "Particle", "Scratch", "Unknown"],
  prediction_label: ["Clean", "Particle", "Scratch"],
  final_class: ["Clean", "Particle", "Scratch", "Unknown"],
};

const activeFilter: ScGlobalFilter = {
  combinator: "and",
  items: [
    {
      id: "class-filter",
      field: "class_number",
      condition: { filterType: "set", values: [2, 3] },
      source: { kind: "manual" },
    },
    {
      id: "area-filter",
      field: "area",
      condition: { filterType: "number", type: "inRange", filter: 120, filterTo: 640 },
      source: { kind: "manual" },
    },
  ],
};

const reclassifyFilter: ScGlobalFilter = {
  combinator: "and",
  items: [
    {
      id: "annotation-filter",
      field: "annotation_label",
      condition: { filterType: "set", values: ["Unknown"] },
      source: { kind: "manual" },
    },
    {
      id: "confidence-filter",
      field: "prediction_confidence",
      condition: { filterType: "number", type: "inRange", filter: 0.6, filterTo: 1 },
      source: { kind: "manual" },
    },
  ],
};

const meta = {
  title: "Features/SC/GlobalFilterModal",
  component: GlobalFilterModal,
  parameters: {
    layout: "fullscreen",
  },
  args: {
    show: true,
    filter: emptyScGlobalFilter(),
    distinctValues: optionSource,
    showReclassifyColumns: false,
  },
  render: (args) => ({
    components: {
      NButton,
      NCard,
      NCode,
      NSpace,
      NTag,
      NText,
      GlobalFilterModal,
    },
    setup() {
      const show = ref(args.show);
      const filter = ref<ScGlobalFilter>(cloneScGlobalFilter(args.filter));
      const distinctValues = ref<Record<string, Array<string | number>>>({
        ...args.distinctValues,
      });
      const activeCount = computed(() => filter.value.items.length);

      function searchOptions(payload: { field: string; search: string }): void {
        const search = payload.search.trim().toLocaleLowerCase();
        const source = optionSource[payload.field] ?? [];
        distinctValues.value = {
          ...distinctValues.value,
          [payload.field]: search
            ? source.filter((value) => String(value).toLocaleLowerCase().includes(search))
            : source,
        };
      }

      return {
        activeCount,
        args,
        distinctValues,
        filter,
        searchOptions,
        show,
      };
    },
    template: `
      <div style="display: grid; place-items: center; min-height: calc(100vh - 32px);">
        <NCard title="Global Filter design sandbox" style="width: min(720px, calc(100vw - 64px));">
          <NSpace vertical :size="16">
            <NText depth="3">
              Apply filters to update the emitted filter state.
            </NText>
            <NSpace align="center">
              <NButton type="primary" @click="show = true">Open Global Filter</NButton>
              <NTag :type="activeCount > 0 ? 'success' : 'default'">
                {{ activeCount }} active condition{{ activeCount === 1 ? "" : "s" }}
              </NTag>
            </NSpace>
            <NCode :code="JSON.stringify(filter, null, 2)" language="json" word-wrap />
          </NSpace>
        </NCard>

        <GlobalFilterModal
          v-model:show="show"
          :filter="filter"
          :distinct-values="distinctValues"
          :show-reclassify-columns="args.showReclassifyColumns"
          @update:filter="filter = $event"
          @search-options="searchOptions"
        />
      </div>
    `,
  }),
} satisfies Meta<typeof GlobalFilterModal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const PreviewFields: Story = {};

export const WithActiveFilters: Story = {
  args: {
    filter: activeFilter,
  },
};

export const DatasetReclassify: Story = {
  args: {
    filter: reclassifyFilter,
    showReclassifyColumns: true,
  },
};
