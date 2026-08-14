import {
  createCollectionApiV1DatasetCollectionsPost,
  deleteCollectionApiV1DatasetCollectionsCollectionIdDelete,
  linkMembersApiV1DatasetCollectionsCollectionIdMembersPost,
} from "@/generated/orval/endpoints/api";
import type {
  Dataset,
  DatasetCollectionMembershipResponse,
  DatasetCollectionResponse,
} from "@/generated/orval/models";

export interface CreateCollectionWithMembersInput {
  name: string;
  description: string;
  targetViewId: string;
  sourceDatasetIds: readonly string[];
}

export interface DatasetCollectionCreationApi {
  create(input: CreateCollectionWithMembersInput): Promise<DatasetCollectionResponse>;
  link(
    collection: DatasetCollectionResponse,
    sourceDatasetIds: readonly string[],
  ): Promise<DatasetCollectionMembershipResponse>;
  remove(collectionId: string): Promise<void>;
}

const defaultApi: DatasetCollectionCreationApi = {
  create: (input) =>
    createCollectionApiV1DatasetCollectionsPost({
      name: input.name,
      description: input.description,
      target_view_id: input.targetViewId,
      duplicate_policy: "keep_all",
      missing_data_policy: "fail",
    }),
  link: (collection, sourceDatasetIds) =>
    linkMembersApiV1DatasetCollectionsCollectionIdMembersPost(collection.id, {
      expected_definition_version: collection.definition_version,
      members: sourceDatasetIds.map((sourceDatasetId, position) => ({
        source_dataset_id: sourceDatasetId,
        position,
        filter_spec: {},
        label_mapping: {},
        sampling_spec: {},
      })),
    }),
  remove: (collectionId) => deleteCollectionApiV1DatasetCollectionsCollectionIdDelete(collectionId),
};

export async function createCollectionWithMembers(
  input: CreateCollectionWithMembersInput,
  api: DatasetCollectionCreationApi = defaultApi,
): Promise<DatasetCollectionResponse> {
  const collection = await api.create(input);
  if (input.sourceDatasetIds.length === 0) return collection;

  try {
    const membership = await api.link(collection, input.sourceDatasetIds);
    return membership.collection;
  } catch (linkError) {
    try {
      await api.remove(collection.id);
    } catch (cleanupError) {
      throw new Error(
        `Collection '${collection.id}' was created without its requested members. Linking failed: ${errorMessage(linkError)}. Automatic cleanup also failed: ${errorMessage(cleanupError)}`,
      );
    }
    throw linkError;
  }
}

export function haveMatchingOrderedLabelSpaces(
  datasets: readonly Pick<Dataset, "task_spec">[],
): boolean {
  if (datasets.length < 2) return true;
  const expected = datasets[0]?.task_spec?.label_space ?? [];
  return datasets.every((dataset) => {
    const labels = dataset.task_spec?.label_space ?? [];
    return (
      labels.length === expected.length && labels.every((label, index) => label === expected[index])
    );
  });
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
