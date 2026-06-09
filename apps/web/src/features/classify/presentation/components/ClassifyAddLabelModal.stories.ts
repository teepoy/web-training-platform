import type { Meta, StoryObj } from "@storybook/vue3";
import { ref, provide } from "vue";
import ClassifyAddLabelModal from "./ClassifyAddLabelModal.vue";
import { CLASSIFY_PAGE_KEY } from "../../application/useClassifyPage";
import type { ClassifyPageState } from "../../application/useClassifyPage";

function createMockPage(): ClassifyPageState {
  const showAddLabelModal = ref(false);
  const newLabelName = ref("");

  return {
    showAddLabelModal,
    newLabelName,
    addNewLabel: () => {
      const trimmed = newLabelName.value.trim();
      if (trimmed) newLabelName.value = "";
    },
    addLabelMutation: { isPending: ref(false), mutate: () => {} },

    datasetId: ref("mock-dataset-1"),
    isReviewMode: ref(false),
    isSparse: ref(false),
    prefs: {} as ClassifyPageState["prefs"],
    themeStyleVars: ref({}),
    datasetQuery: {} as ClassifyPageState["datasetQuery"],
    router: {} as ClassifyPageState["router"],
    selectedTrainerId: ref(null),
    trainerOptions: ref([]),
    startTraining: () => {},
    startTrainingMutation: { isPending: ref(false), mutate: () => {} },
    activeTrainingJob: ref(null),
    selectedModelId: ref(null),
    modelOptions: ref([]),
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
  component: ClassifyAddLabelModal,
  title: "Classify/ClassifyAddLabelModal",
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
} satisfies Meta<typeof ClassifyAddLabelModal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
