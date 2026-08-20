import { flushPromises } from "@vue/test-utils";
import { defineComponent, h, provide, ref } from "vue";
import { NMessageProvider } from "naive-ui";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type {
  TaskTrackerDetailResponse,
  TaskTrackerSummaryResponse,
} from "@/generated/orval/models";
import { mountWithProviders } from "@/testing";
import { server } from "@/testing/msw/server";

import TaskInsightModal, { TASK_INSIGHT_ORG_ID_KEY } from "./TaskInsightModal.vue";

const task: TaskTrackerSummaryResponse = {
  id: "task-1",
  task_kind: "prediction",
  execution_kind: "prefect",
  display_name: "Prediction task",
  display_status: "completed",
  stage: "validation_output",
  dataset_id: "dataset-1",
  created_by: "user-1",
  created_at: "2026-08-20T01:00:00Z",
  updated_at: "2026-08-20T01:01:00Z",
};

const detail: TaskTrackerDetailResponse = {
  id: task.id,
  task_kind: task.task_kind,
  raw: {
    platform_job: {},
    logs: [],
  },
  derived: {
    task_kind: task.task_kind,
    execution_kind: task.execution_kind,
    display_status: task.display_status,
    stage: task.stage,
    stages: [],
    scorecard: {
      errors: 1,
      warnings: 2,
      checks: [
        {
          key: "predictions",
          label: "Predictions",
          status: "warning",
          message: "One sample needs attention",
        },
      ],
    },
    artifacts: [{ id: "artifact-1", kind: "parquet" }],
    dynamic_console_lines: ["processed 100 samples"],
  },
};

const Host = defineComponent({
  setup() {
    provide(TASK_INSIGHT_ORG_ID_KEY, ref("org-1"));
    return () =>
      h(NMessageProvider, null, {
        default: () =>
          h(TaskInsightModal, {
            show: true,
            task,
            handoffEnabled: false,
          }),
      });
  },
});

describe("TaskInsightModal", () => {
  it("shows runtime output and validation details", async () => {
    server.use(http.get("/api/v1/task-tracker/tasks/task-1", () => HttpResponse.json(detail)));

    const { wrapper } = await mountWithProviders(Host);
    await flushPromises();

    const modalText = document.body.textContent ?? "";
    expect(modalText).toContain("Dynamic Console");
    expect(modalText).toContain("processed 100 samples");
    expect(modalText).toContain("Validation & Output");
    expect(modalText).toContain("One sample needs attention");
    expect(modalText).toContain("Artifacts");

    wrapper.unmount();
  });
});
