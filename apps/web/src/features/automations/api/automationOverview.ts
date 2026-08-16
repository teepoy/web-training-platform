import {
  listAutomationRunsApiV1AutomationsGet,
  retryPredictionBatchApiV1DatasetCollectionsCollectionIdPredictionBatchesBatchIdRetryPost,
} from "@/generated/orval/endpoints/api";
import type {
  AutomationRunOverviewResponse,
  ListAutomationRunsApiV1AutomationsGetParams,
  PaginatedResponseAutomationRunOverviewResponse,
} from "@/generated/orval/models";

export type AutomationRecipeKind = "discovery" | "backfill" | "retry" | "prediction";
export type AutomationRunOverview = AutomationRunOverviewResponse;
export type AutomationRunPage = PaginatedResponseAutomationRunOverviewResponse;
export type AutomationOverviewFilters = ListAutomationRunsApiV1AutomationsGetParams;

export function listAutomationRuns(filters: AutomationOverviewFilters): Promise<AutomationRunPage> {
  return listAutomationRunsApiV1AutomationsGet(filters);
}

export function retryAutomationRun(run: AutomationRunOverview): Promise<unknown> {
  if (!run.retry_supported) {
    return Promise.reject(new Error("This run has no retryable work"));
  }
  if (run.run_source !== "prediction_batch") {
    return Promise.reject(new Error("Open the Collection to recover this data update"));
  }
  return retryPredictionBatchApiV1DatasetCollectionsCollectionIdPredictionBatchesBatchIdRetryPost(
    run.target_id,
    run.id,
  );
}
