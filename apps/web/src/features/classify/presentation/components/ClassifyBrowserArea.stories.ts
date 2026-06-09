import type { Meta, StoryObj } from "@storybook/vue3";
import { ref, provide, shallowReactive } from "vue";
import ClassifyBrowserArea from "./ClassifyBrowserArea.vue";
import { CLASSIFY_PAGE_KEY } from "../../application/useClassifyPage";
import type { ClassifyPageState } from "../../application/useClassifyPage";
import ClassifySidebar from "./ClassifySidebar.vue";
import { defaultPanels } from "../../config";

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
    ClassifySidebar: ClassifySidebar,
    TaskInsightModal: {} as ClassifyPageState["TaskInsightModal"],
  };
}

const meta = {
  component: ClassifyBrowserArea,
  title: "Classify/ClassifyBrowserArea",
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
} satisfies Meta<typeof ClassifyBrowserArea>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
