import type { Meta, StoryObj } from "@storybook/vue3";
import type { TaskTrackerSummaryResponse as TaskTrackerSummary } from "@/generated/orval/models";
import TaskInsightModal from "./TaskInsightModal.vue";

const mockTask: TaskTrackerSummary = {
  id: "task-mock-001",
  task_kind: "training",
  execution_kind: "prefect",
  display_name: "ResNet-50 Fine-tune",
  display_status: "running",
  stage: "execution",
  dataset_id: "ds-mock-001",
  model_id: "model-mock-001",
  trainer_id: "trainer-resnet",
  created_by: "user-mock-001",
  created_at: "2026-05-24T08:00:00Z",
  updated_at: "2026-05-24T08:15:00Z",
  prefect_state: "RUNNING",
  work_pool_name: "default",
  work_queue_name: "gpu",
  queue_priority: 1,
  queue_priority_label: "high",
  queue_depth_ahead: 0,
  capacity_status: "normal",
  pool_concurrency_limit: 4,
  pool_slots_used: 2,
};

const meta = {
  title: "Shared/TaskInsightModal",
  component: TaskInsightModal,
  args: {
    show: true,
    task: mockTask,
    handoffEnabled: false,
  },
} satisfies Meta<typeof TaskInsightModal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
