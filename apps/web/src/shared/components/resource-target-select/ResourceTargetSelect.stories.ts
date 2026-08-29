import { ref } from "vue";
import type { Meta, StoryObj } from "@storybook/vue3";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import {
  getListCollectionsApiV1DatasetCollectionsGetUrl,
  getListRevisionsApiV1DatasetCollectionsCollectionIdRevisionsGetUrl,
} from "@/generated/orval/endpoints/api";
import { provideFetchMock } from "../../../../.storybook/support/mocks";
import ResourceTargetSelect from "./ResourceTargetSelect.vue";
import type { ResourceTargetSelection } from "./types";

const collectionId = "collection-august-lots";

const meta: Meta<typeof ResourceTargetSelect> = {
  title: "Resources/ResourceTargetSelect",
  component: ResourceTargetSelect,
  decorators: [
    provideFetchMock([
      {
        urlPattern:
          getListRevisionsApiV1DatasetCollectionsCollectionIdRevisionsGetUrl(collectionId),
        response: {
          body: [
            {
              id: "revision-3",
              collection_id: collectionId,
              revision_number: 3,
              definition_version: 3,
              definition_hash: "hash-3",
              target_view_id: "patch_image_v1",
              target_view_contract: "sc.patch-image",
              target_schema_version: "1",
              status: "ready",
              source_snapshot: [],
              row_count: 1240,
              label_counts: {},
              manifest_uri: "s3://collections/revision-3.json",
              provenance_uri: null,
              manifest_format: "json",
              source_resolution: "observed_membership",
              reproducibility_capability: true,
              trigger_kind: "manual",
              trigger_ref: null,
              created_by: "user-1",
              created_at: "2026-08-29T08:00:00Z",
              error_code: null,
              error_detail: null,
            },
          ],
        },
      },
      {
        urlPattern: getListCollectionsApiV1DatasetCollectionsGetUrl(),
        response: {
          body: {
            items: [
              {
                id: collectionId,
                org_id: "org-1",
                name: "August production lots",
                description: "Cross-line inspection snapshot",
                target_view_id: "patch_image_v1",
                target_view_contract: "sc.patch-image",
                target_schema_version: "1",
                duplicate_policy: "keep_first",
                missing_data_policy: "fail",
                definition_version: 3,
                created_by: "user-1",
                created_at: "2026-08-20T08:00:00Z",
                updated_at: "2026-08-29T08:00:00Z",
                default_model_id: null,
                model_binding_version: 1,
              },
            ],
            total: 1,
          },
        },
      },
    ]),
  ],
  parameters: { layout: "padded" },
};

export default meta;
type Story = StoryObj<typeof ResourceTargetSelect>;

export const CollectionSnapshotPinned: Story = {
  render: () => ({
    components: { ResourceTargetSelect },
    setup() {
      useAuthStore().user = {
        id: "user-1",
        email: "user@example.com",
        name: "Current User",
        is_superadmin: false,
        created_at: "2026-01-01T00:00:00Z",
      };
      useOrgStore().currentOrgId = "org-1";
      const target = ref<ResourceTargetSelection | null>({
        kind: "collection",
        id: collectionId,
        name: "August production lots",
        viewTypes: ["patch_image_v1"],
        revisionId: "revision-3",
        revisionNumber: 3,
      });
      return { target };
    },
    template: '<ResourceTargetSelect v-model="target" :active="true" />',
  }),
};
