import {
  ref,
  onMounted,
  computed,
  provide,
  inject,
  type Ref,
  type ComputedRef,
  type InjectionKey,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { useMessage } from "naive-ui";
import {
  injectWaferPanelData,
  metadataNumber,
  metadataString,
} from "@/shared/composables/useWaferHelpers";
import { createDataPipeline, DATA_PIPELINE_KEY } from "@/shared/composables/useDataPipeline";
import type { SidebarPanelDescriptor } from "@/shared/types/components";
import { useSampleBrowserPrefs } from "@/shared/stores/sampleBrowser";
import type { BrowserItem, WaferPoint } from "@/shared/types/components";
import { previewPanels } from "../config";
import {
  getPreviewSessionApiV1PreviewSessionsSessionIdGet,
  startPreviewPersistApiV1PreviewSessionsSessionIdPersistPost,
} from "@/generated/orval/endpoints/api";
import type { PreviewItem, PreviewPersistScope, PreviewPersistStatus, PreviewSession } from '@/shared/api/preview';
import { usePreviewLoader } from "@/shared/composables/usePreviewLoader";

export const PREVIEW_PAGE_KEY: InjectionKey<PreviewPageState> =
  Symbol("previewPage");

export interface PreviewPageState {
  sessionId: Ref<string>;
  session: Ref<PreviewSession | null>;
  sessionError: Ref<string | null>;
  sessionLoading: Ref<boolean>;

  loader: ReturnType<typeof usePreviewLoader>;

  showPersistModal: Ref<boolean>;
  persistScope: Ref<PreviewPersistScope>;
  isPersisting: Ref<boolean>;

  selectedItem: Ref<PreviewItem | null>;
  showDrawer: Ref<boolean>;

  browserItems: Ref<BrowserItem[]>;
  previewSidebarPanels: ComputedRef<SidebarPanelDescriptor[]>;
  prefs: ReturnType<typeof useSampleBrowserPrefs>;

  selectItem: (item: PreviewItem) => void;
  handlePersist: () => Promise<void>;
}

export function usePreviewPage() {
  const route = useRoute();
  const router = useRouter();
  const message = useMessage();
  const prefs = useSampleBrowserPrefs();

  const sessionId = computed(() => route.params.sessionId as string);

  const session = ref<PreviewSession | null>(null);
  const sessionError = ref<string | null>(null);
  const sessionLoading = ref(true);

  const loader = usePreviewLoader({
    sessionId: sessionId.value,
    pageSize: 20,
  });

  const showPersistModal = ref(false);
  const persistScope = ref<PreviewPersistScope>("entire_collection");
  const isPersisting = ref(false);

  const selectedItem = ref<PreviewItem | null>(null);
  const showDrawer = ref(false);

  const browserItems = computed<BrowserItem[]>(() => {
    return loader.items.value.map((item) => ({
      id: item.upstream_item_id,
      imageSrcs: item.image_uris,
      metadata: item.metadata || {},
      sourceKind: "preview" as const,
      currentLabel: null,
      draftLabel: null,
      predictionLabel: null,
      predictionConfidence: null,
      predictionId: null,
      activationLabel: null,
    }));
  });

  const pipeline = createDataPipeline<BrowserItem>(browserItems);
  pipeline.register("wafer-map");
  provide(DATA_PIPELINE_KEY, pipeline);

  const previewWaferPoints = computed<WaferPoint[]>(() => {
    return loader.items.value.flatMap((item) => {
      const x = metadataNumber(item.metadata, "wafer_x");
      const y = metadataNumber(item.metadata, "wafer_y");
      if (x == null || y == null) {
        return [];
      }
      return [
        {
          id: metadataString(item.metadata, "point_id") ?? item.upstream_item_id,
          x,
          y,
        },
      ];
    });
  });

  const previewSidebarPanels = computed(() =>
    injectWaferPanelData(previewPanels, previewWaferPoints.value, "browser-items"),
  );

  function selectItem(item: PreviewItem) {
    selectedItem.value = item;
    showDrawer.value = true;
  }

  onMounted(async () => {
    try {
      const { data } = await getPreviewSessionApiV1PreviewSessionsSessionIdGet(sessionId.value);
      session.value = data as PreviewSession;
      await loader.loadMore();
    } catch {
      sessionError.value = "Preview session not found or expired.";
    } finally {
      sessionLoading.value = false;
    }
  });

  async function handlePersist() {
    isPersisting.value = true;
    try {
      const { data } = await startPreviewPersistApiV1PreviewSessionsSessionIdPersistPost(
        sessionId.value,
        { scope: persistScope.value },
      );
      const status = data as PreviewPersistStatus;
      showPersistModal.value = false;
      message.success("Dataset persisted successfully!");
      await router.push(
        `/datasets/${status.dataset_id}/classify?previewPersistSession=${sessionId.value}`,
      );
    } catch (err) {
      message.error("Failed to persist: " + String(err));
    } finally {
      isPersisting.value = false;
    }
  }

  const state: PreviewPageState = {
    sessionId,
    session,
    sessionError,
    sessionLoading,
    loader,
    showPersistModal,
    persistScope,
    isPersisting,
    selectedItem,
    showDrawer,
    browserItems,
    previewSidebarPanels,
    prefs,
    selectItem,
    handlePersist,
  };

  provide(PREVIEW_PAGE_KEY, state);

  return state;
}

export function injectPreviewPage(): PreviewPageState {
  const page = inject(PREVIEW_PAGE_KEY);
  if (!page) throw new Error("PreviewPageState not provided");
  return page;
}
