import type { Meta, StoryObj } from "@storybook/vue3";
import { ref, provide } from "vue";
import ClassifyWorkflowCards from "./ClassifyWorkflowCards.vue";
import { CLASSIFY_PAGE_KEY } from "../../application/useClassifyPage";
import type { ClassifyPageState } from "../../application/useClassifyPage";

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
    predictionJobs: ref([]),
    predictionJobColumns: ref([]),
    filteredBrowserItems: ref([]),
    activeTotalCount: ref(0),
    activeGridLoading: ref(false),
    onBrowserSelect: () => {},
    onGridLoadMore: () => {},
    onKeyDown: () => {},
    browserShellRef: ref(null),
    labelSearch: ref(""),
    filteredLabels: ref([]),
    labelColor: () => "#999",
    browserSubmitCount: ref(0),
    isSubmitting: ref(false),
    submitFromGrid: () => {},
    labelFilter: ref(null),
    filterOptions: ref([]),
    orderBy: ref("id"),
    orderOptions: [],
    syncCollectionMutation: { isPending: ref(false), mutate: () => {} },
    syncCollectionToLs: () => {},
    resetReviewEdits: () => {},
    clearPredictionReview: () => {},
    mergedPanels: ref([]),
    pageDashboard: {},
    showAddLabelModal: ref(false),
    newLabelName: ref(""),
    addLabelMutation: { isPending: ref(false), mutate: () => {} },
    addNewLabel: () => {},
    showTaskModal: ref(false),
    activeTaskSummary: ref(null),
    taskHandoffEnabled: ref(true),
    gridRef: ref(null),
    applyLabelToSelection: () => {},
    ClassifySidebar: {} as ClassifyPageState["ClassifySidebar"],
    TaskInsightModal: {} as ClassifyPageState["TaskInsightModal"],
  };
}

const meta = {
  component: ClassifyWorkflowCards,
  title: "Classify/ClassifyWorkflowCards",
  parameters: {
    backgrounds: { default: "light" },
  },
  decorators: [
    () => ({
      setup() {
        provide(CLASSIFY_PAGE_KEY, createMockPage());
      },
      template: "<story />",
    }),
  ],
} satisfies Meta<typeof ClassifyWorkflowCards>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
