import {
  createTrainingJobApiV1TrainingJobsPost,
  updateLabelSpaceApiV1DatasetsDatasetIdLabelSpacePatch,
} from "@/generated/orval/endpoints/api";
import type { TrainingJob } from "@/generated/orval/models";

export async function startTrainingAction(
  datasetId: string,
  trainerId: string,
): Promise<TrainingJob> {
  return createTrainingJobApiV1TrainingJobsPost({
    dataset_id: datasetId,
    trainer_id: trainerId,
  });
}

export async function addLabelAction(
  datasetId: string,
  newLabel: string,
  currentLabels: string[],
): Promise<unknown> {
  if (currentLabels.includes(newLabel)) {
    throw new Error(`Label "${newLabel}" already exists`);
  }
  return updateLabelSpaceApiV1DatasetsDatasetIdLabelSpacePatch(datasetId, {
    label_space: [...currentLabels, newLabel],
  });
}
