export type ResourceTargetSelection =
  | {
      kind: "dataset";
      id: string;
      name: string;
      viewTypes: string[];
    }
  | {
      kind: "collection";
      id: string;
      name: string;
      viewTypes: string[];
      revisionId: string;
      revisionNumber: number;
    };

export type ResourceTargetRequestFields =
  | { dataset_id: string }
  | { collection_id: string; collection_revision_id: string };

export interface CollectionRevisionCandidate {
  id: string;
  status: string;
  revision_number: number;
}

export function latestReadyCollectionRevision<T extends CollectionRevisionCandidate>(
  revisions: T[],
): T | undefined {
  return [...revisions]
    .filter((revision) => revision.status === "ready")
    .sort((left, right) => right.revision_number - left.revision_number)[0];
}

export function resourceTargetRequestFields(
  target: ResourceTargetSelection,
): ResourceTargetRequestFields {
  return target.kind === "dataset"
    ? { dataset_id: target.id }
    : { collection_id: target.id, collection_revision_id: target.revisionId };
}
