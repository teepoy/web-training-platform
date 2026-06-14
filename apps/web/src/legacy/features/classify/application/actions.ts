import { createTrainingJobApiV1TrainingJobsPost } from "@/generated/orval/endpoints/api";
import { updateLabelSpace } from "@/shared/api/datasets";
import type { TrainingJob } from "@/generated/orval/models";

export async function startTrainingAction(
  datasetId: string,
  trainerId: string,
): Promise<TrainingJob> {
  const { data } = await createTrainingJobApiV1TrainingJobsPost({ dataset_id: datasetId, trainer_id: trainerId });
  return data as TrainingJob;
}

export async function addLabelAction(
  datasetId: string,
  newLabel: string,
  currentLabels: string[],
): Promise<unknown> {
  if (currentLabels.includes(newLabel)) {
    throw new Error(`Label "${newLabel}" already exists`);
  }
  return updateLabelSpace(datasetId, [...currentLabels, newLabel]);
}
