import { ref } from "vue";
import type { Meta, StoryObj } from "@storybook/vue3";
import { NButton, NSpace } from "naive-ui";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import {
  getListModelCreatorsApiV1ModelsCreatorsGetUrl,
  getListModelsApiV1ModelsGetUrl,
} from "@/generated/orval/endpoints/api";
import { provideFetchMock } from "../../../../../.storybook/support/mocks";
import ModelSearchSurface from "./ModelSearchSurface.vue";

const models = [
  {
    id: "model-dataset-1",
    uri: "s3://models/dataset-1.pt",
    kind: "model",
    name: "Wafer defect baseline",
    job_id: "job-1",
    trainer_name: "YOLO SC",
    dataset_id: "dataset-1",
    dataset_name: "Line 7 inspection",
    created_by: "user-1",
    creator_name: "Current User",
    created_at: "2026-08-29T08:10:00Z",
  },
  {
    id: "model-collection-1",
    uri: "s3://models/collection-1.pt",
    kind: "model",
    name: "Cross-lot classifier",
    job_id: "job-2",
    trainer_name: "YOLO SC",
    collection_id: "collection-1",
    collection_name: "August production lots",
    collection_revision_id: "revision-3",
    created_by: "user-2",
    creator_name: "Quality Team",
    created_at: "2026-08-28T14:30:00Z",
  },
];

const meta: Meta<typeof ModelSearchSurface> = {
  title: "Models/ModelSearchSurface",
  component: ModelSearchSurface,
  decorators: [
    provideFetchMock([
      {
        urlPattern: getListModelCreatorsApiV1ModelsCreatorsGetUrl(),
        response: {
          body: [
            { id: "user-1", name: "Current User" },
            { id: "user-2", name: "Quality Team" },
          ],
        },
      },
      {
        urlPattern: getListModelsApiV1ModelsGetUrl(),
        response: { body: { items: models, total: models.length } },
      },
    ]),
  ],
  parameters: { layout: "padded" },
};

export default meta;
type Story = StoryObj<typeof ModelSearchSurface>;

function prepareSession(): void {
  useAuthStore().user = {
    id: "user-1",
    email: "user@example.com",
    name: "Current User",
    is_superadmin: false,
    created_at: "2026-01-01T00:00:00Z",
  };
  useOrgStore().currentOrgId = "org-1";
}

export const Management: Story = {
  render: () => ({
    components: { ModelSearchSurface, NButton, NSpace },
    setup() {
      prepareSession();
      const checked = ref([]);
      return { checked };
    },
    template: `
      <ModelSearchSurface v-model:checked-row-keys="checked" mode="management" :active="true">
        <template #row-actions>
          <NSpace :size="6" :wrap="false">
            <NButton size="small" quaternary>Rename</NButton>
            <NButton size="small" quaternary type="error">Delete</NButton>
          </NSpace>
        </template>
      </ModelSearchSurface>
    `,
  }),
};

export const CollectionCompatiblePicker: Story = {
  render: () => ({
    components: { ModelSearchSurface },
    setup() {
      prepareSession();
      const selected = ref<string | null>("model-collection-1");
      return { selected };
    },
    template: `
      <ModelSearchSurface
        v-model="selected"
        mode="selection"
        :active="true"
        :compatible-view-ids="['patch_image_v1', 'review_image_v1']"
        :max-height="320"
      />
    `,
  }),
};
