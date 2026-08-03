import type { Meta, StoryObj } from "@storybook/vue3";
import { computed, ref } from "vue";
import { NButton, NCard, NCode, NSpace, NTag, NText } from "naive-ui";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";
import ScGlobalFilterModal from "./ScGlobalFilterModal.vue";

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

const activeFilter: ScSampleTableFilter = {
  class_number: {
    filterType: "set",
    values: [2, 3],
  },
  area: {
    filterType: "number",
    type: "inRange",
    filter: 120,
    filterTo: 640,
  },
};

const reclassifyFilter: ScSampleTableFilter = {
  annotation_label: {
    filterType: "set",
    values: ["Unknown"],
  },
  prediction_confidence: {
    filterType: "number",
    type: "inRange",
    filter: 0.6,
    filterTo: 1,
  },
};

const meta = {
  title: "Features/SC/GlobalFilterModal",
  component: ScGlobalFilterModal,
  parameters: {
    layout: "fullscreen",
  },
  args: {
    show: true,
    filter: {},
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
      ScGlobalFilterModal,
    },
    setup() {
      const show = ref(args.show);
      const filter = ref<ScSampleTableFilter>({ ...args.filter });
      const distinctValues = ref<Record<string, Array<string | number>>>({
        ...args.distinctValues,
      });
      const activeCount = computed(() => Object.keys(filter.value).length);

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
              Open the modal, configure fields, then close it to inspect the emitted filter state.
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

        <ScGlobalFilterModal
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
} satisfies Meta<typeof ScGlobalFilterModal>;

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
