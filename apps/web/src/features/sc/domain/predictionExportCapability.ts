type ScPredictionExportCandidate = {
  dataset_type?: string | null;
  storage_mode?: string | null;
  task_spec?: { task_type?: unknown } | null;
};

export function supportsScPredictionExport(dataset: ScPredictionExportCandidate | null): boolean {
  return (
    dataset?.dataset_type === "image_sc" &&
    dataset.task_spec?.task_type === "sc" &&
    dataset.storage_mode === "file_shard_sparse"
  );
}
