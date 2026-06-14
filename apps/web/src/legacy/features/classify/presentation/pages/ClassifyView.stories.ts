import type { Meta, StoryObj } from "@storybook/vue3";
import { ref, provide, shallowReactive, h } from "vue";
import { NButton } from "naive-ui";
import ClassifyView from "./ClassifyView.vue";
import { CLASSIFY_PAGE_KEY } from "../../application/useClassifyPage";
import type { ClassifyPageState } from "../../application/useClassifyPage";
import ClassifySidebar from "../components/ClassifySidebar.vue";
import { defaultPanels } from "../../config";
import type { DataTableColumns } from "naive-ui";
import type { PredictionJobResponse as PredictionJob } from "@/generated/orval/models";

const mockPredictionJobs: PredictionJob[] = [
  {
    id: "pred-job-001",
    dataset_id: "mock-dataset-1",
    model_id: "model-a",
    status: "completed",
    created_by: "user-1",
    created_at: "2026-05-20T10:00:00Z",
    updated_at: "2026-05-20T10:05:00Z",
    external_job_id: null,
    summary: { total_samples: 100, processed: 100, successful: 95 },
    model_version: "v1",
    target: "labeled_image_v1",
    sample_ids: [],
  },
  {
    id: "pred-job-002",
    dataset_id: "mock-dataset-1",
    model_id: "model-b",
    status: "running",
    created_by: "user-1",
    created_at: "2026-05-21T14:30:00Z",
    updated_at: "2026-05-21T14:35:00Z",
    external_job_id: null,
    summary: { total_samples: 100, processed: 45, successful: 0 },
    model_version: "v2",
    target: "labeled_image_v1",
    sample_ids: [],
  },
];

const mockColumns: DataTableColumns<PredictionJob> = [
  { title: "Job", key: "id", width: 180 },
  { title: "Status", key: "status", width: 120 },
  {
    title: "Progress",
    key: "progress",
    width: 120,
    render: () => "",
  },
  {
    title: "Actions",
    key: "actions",
    width: 100,
    render: () => h(NButton, { size: "small" }, { default: () => "Load" }),
  },
];

function createMockPage(): ClassifyPageState {
  return {
    datasetId: ref("mock-dataset-1"),
    isReviewMode: ref(false),
    isSparse: ref(false),
    prefs: {} as ClassifyPageState["prefs"],
    themeStyleVars: ref({}),
    datasetQuery: {} as ClassifyPageState["datasetQuery"],
    router: {} as ClassifyPageState["router"],

    selectedTrainerId: ref(null),
    trainerOptions: ref([
      { label: "Default Training", value: "trainer-default" },
      { label: "Fast Training", value: "trainer-fast" },
    ]),
    startTraining: () => {},
    startTrainingMutation: { isPending: ref(false), mutate: () => {} },
    activeTrainingJob: ref(null),

    selectedModelId: ref(null),
    modelOptions: ref([
      { label: "Model A", value: "model-a" },
      { label: "Model B", value: "model-b" },
    ]),
    modelVersionTag: ref(""),
    runPredictions: () => {},
    runPredictionsMutation: { isPending: ref(false), mutate: () => {} },
    activePredictionJob: ref(null),
    cancelPrediction: () => {},
    cancelPredictionMutation: { isPending: ref(false), mutate: () => {} },
    formatPredictionJobProgress: () => "",

    predictionJobs: ref(mockPredictionJobs),
    predictionJobColumns: ref(mockColumns),

    filteredBrowserItems: ref([]),
    activeTotalCount: ref(0),
    activeGridLoading: ref(false),
    onBrowserSelect: () => {},
    onGridLoadMore: () => {},
    onKeyDown: () => {},
    browserShellRef: ref(null),

    labelSearch: ref(""),
    filteredLabels: ref(["cat", "dog", "bird", "fish", "rabbit"]),
    labelColor: (label: string) => {
      const colors: Record<string, string> = {
        cat: "#4CAF50",
        dog: "#2196F3",
        bird: "#FF9800",
        fish: "#E91E63",
        rabbit: "#9C27B0",
      };
      return colors[label] ?? "#607D8B";
    },
    browserSubmitCount: ref(5),
    isSubmitting: ref(false),
    submitFromGrid: () => {},

    labelFilter: ref(null),
    filterOptions: ref([
      { label: "All labels", value: null },
      { label: "cat", value: "cat" },
      { label: "dog", value: "dog" },
      { label: "bird", value: "bird" },
    ]),
    orderBy: ref("id"),
    orderOptions: [
      { label: "Default Order", value: "id" },
      { label: "Recent", value: "created_at" },
    ],

    syncCollectionMutation: { isPending: ref(false), mutate: () => {} },
    syncCollectionToLs: () => {},
    resetReviewEdits: () => {},
    clearPredictionReview: () => {},

    mergedPanels: ref(defaultPanels),
    pageDashboard: shallowReactive({}),

    showAddLabelModal: ref(false),
    newLabelName: ref(""),
    addLabelMutation: { isPending: ref(false), mutate: () => {} },
    addNewLabel: () => {},

    showTaskModal: ref(false),
    activeTaskSummary: ref(null),
    taskHandoffEnabled: ref(true),

    gridRef: ref(null),
    applyLabelToSelection: () => {},

    ClassifySidebar,
    TaskInsightModal: {} as ClassifyPageState["TaskInsightModal"],
  };
}

const meta = {
  component: ClassifyView,
  title: "Classify/ClassifyView",
  parameters: {
    backgrounds: { default: "light" },
  },
  decorators: [
    () => ({
      setup() {
        provide(CLASSIFY_PAGE_KEY, createMockPage());
      },
      template: '<div style="height: 100vh; overflow: hidden;"><story /></div>',
    }),
  ],
} satisfies Meta<typeof ClassifyView>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
