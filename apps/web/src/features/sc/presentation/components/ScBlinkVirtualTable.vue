<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from "vue";
import type { CSSProperties } from "vue";
import { tableFromIPC } from "apache-arrow";
import {
  NSwitch,
  NText,
  NRadioGroup,
  NRadioButton,
  NButton,
  NTag,
  NSelect,
  NInput,
  NModal,
  NImage,
} from "naive-ui";
import { withAuthQueryParams } from "@/shared/api/client";
import { useBlinkController } from "@/shared/composables/useBlinkController";
import {
  useBlinkVirtualScroll,
  ROW_PADDING_Y,
  MINI_HEADER_HEIGHT,
} from "@/features/sc/presentation/composables/useBlinkVirtualScroll";
import { useBlinkRubberBand } from "@/features/sc/presentation/composables/useBlinkRubberBand";
import { scSampleImageUrl } from "@/features/sc/domain/models";
import type { PerspectiveViewSnapshot } from "@/features/sc/presentation/components/composables/useManagedPerspectiveView";
import { usePagedPerspectiveGallery } from "@/features/sc/presentation/components/composables/usePagedPerspectiveGallery";

interface BlinkSample {
  rowIndex: number;
  sampleId?: string | null;
  defectId: number;
  reviewImages: number[];
  annotationLabel: string | null;
  predictionLabel: string | null;
  predictionConfidence: number | null;
}

interface ScBlinkVirtualTableProps {
  patchViewSnapshot?: PerspectiveViewSnapshot | null;
  reviewViewSnapshot?: PerspectiveViewSnapshot | null;
  loading?: boolean;
  datasetId?: string | null;
  patchSamplesPerRow?: number;
  reviewSamplesPerRow?: number;
  patchCellSize?: number;
  reviewCellSize?: number;
  cellGap?: number;
  rowGap?: number;
  selectedDefectIds?: Set<string> | string[];
  annotationDrafts?: Record<string, string>;
  showPredictionBadges?: boolean;
  overscan?: number;
  blinkIntervalMs?: number;
  initialBlinkEnabled?: boolean;
  showModeSwitch?: boolean;
  inspectionTime: string;
  waferKey: number;
}

const props = withDefaults(defineProps<ScBlinkVirtualTableProps>(), {
  patchSamplesPerRow: 4,
  reviewSamplesPerRow: 1,
  patchCellSize: 64,
  reviewCellSize: 128,
  cellGap: 4,
  rowGap: 12,
  selectedDefectIds: () => new Set<string>(),
  annotationDrafts: () => ({}),
  showPredictionBadges: false,
  overscan: 10,
  blinkIntervalMs: 1000,
  initialBlinkEnabled: true,
  showModeSwitch: true,
});

const emit = defineEmits<{
  selectSamples: [
    defectIds: string[],
    modifiers: {
      shift: boolean;
      ctrl: boolean;
      meta: boolean;
      selectionMode?: "replace" | "add" | "toggle";
    },
  ];
  modeChange: [mode: "patch" | "review"];
}>();

const showDefectIdLabel = ref(true);
const mode = ref<"patch" | "review">("patch");

watch(mode, (value) => emit("modeChange", value), { immediate: true });
const settingsOpen = ref(false);
const MAX_SAMPLES_PER_ROW = 30;
const clampSamplesPerRow = (value: number): number =>
  Math.min(MAX_SAMPLES_PER_ROW, Math.max(1, value));
const patchPerRow = ref(clampSamplesPerRow(props.patchSamplesPerRow));
const reviewPerRow = ref(clampSamplesPerRow(props.reviewSamplesPerRow));
const IMAGE_SIZE_OPTIONS = [32, 64, 128, 256, 512] as const;
const IMAGE_SIZE_SELECT_OPTIONS = IMAGE_SIZE_OPTIONS.map((size) => ({
  label: `${size}`,
  value: size,
}));
type ImageSizeOption = (typeof IMAGE_SIZE_OPTIONS)[number];
type PatchImageType = "Defective" | "Reference" | "Difference";
const PATCH_IMAGE_LABELS: Record<PatchImageType, string> = {
  Defective: "Defective",
  Reference: "Reference",
  Difference: "Difference",
};
const PATCH_IMAGE_SPRITE_TOKENS: Record<PatchImageType, string> = {
  Defective: "patchDefective",
  Reference: "patchReference",
  Difference: "patchDifference",
};
const DEFAULT_PATCH_IMAGE_TYPES: PatchImageType[] = ["Defective", "Reference", "Difference"];
const patchImageTypeByInput: Record<string, PatchImageType> = {
  defective: "Defective",
  reference: "Reference",
  template: "Reference",
  difference: "Difference",
};
const normalizeImageSize = (value: number | undefined): ImageSizeOption =>
  IMAGE_SIZE_OPTIONS.includes(value as ImageSizeOption) ? (value as ImageSizeOption) : 64;
const patchImageSize = ref<ImageSizeOption>(normalizeImageSize(props.patchCellSize));
const reviewImageSize = ref<ImageSizeOption>(normalizeImageSize(props.reviewCellSize));
const patchImagesInput = ref(DEFAULT_PATCH_IMAGE_TYPES.join(","));
const patchDefectiveEnabled = ref(true);
const patchReferenceEnabled = ref(true);
const patchDifferenceEnabled = ref(true);

function rebuildPatchImagesInput() {
  const parts: string[] = [];
  if (patchDefectiveEnabled.value) parts.push("Defective");
  if (patchReferenceEnabled.value) parts.push("Reference");
  if (patchDifferenceEnabled.value) parts.push("Difference");
  patchImagesInput.value = parts.join(",");
}

const reviewImagesInput = ref("");
const reviewImagesInputEdited = ref(false);
const imageSize = computed({
  get: () => (mode.value === "patch" ? patchImageSize.value : reviewImageSize.value),
  set: (value: number) => {
    const normalized = normalizeImageSize(value);
    if (mode.value === "patch") {
      patchImageSize.value = normalized;
    } else {
      reviewImageSize.value = normalized;
    }
  },
});
const samplesPerRow = computed({
  get: () => (mode.value === "patch" ? patchPerRow.value : reviewPerRow.value),
  set: (value: number) => {
    if (mode.value === "patch") {
      patchPerRow.value = clampSamplesPerRow(value);
    } else {
      reviewPerRow.value = clampSamplesPerRow(value);
    }
  },
});

function adjustSamplesPerRow(delta: number): void {
  samplesPerRow.value += delta;
}

function numeric(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function stringOrNull(value: unknown): string | null {
  if (value == null || value === "") return null;
  return String(value);
}

function parseReviewImages(value: unknown): number[] {
  if (Array.isArray(value)) return value.map(Number).filter(Number.isFinite);
  if (typeof value !== "string" || value.length === 0) return [];
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.map(Number).filter(Number.isFinite);
  } catch {
    return [];
  }
}

const EMPTY_REVIEW_IMAGES: number[] = [];

function samplesFromArrow(data: unknown, offset: number, review: boolean): BlinkSample[] {
  const table = tableFromIPC(data as Uint8Array);
  const defectIds = table.getChild("defect_id");
  const sampleIds = table.getChild("sample_id");
  const reviewImages = table.getChild("review_image_ids_json");
  const annotationLabels = table.getChild("annotation_label");
  const predictionLabels = table.getChild("prediction_label");
  const predictionConfidences = table.getChild("prediction_confidence");

  return Array.from({ length: table.numRows }, (_, index) => {
    const confidence = predictionConfidences?.get(index);
    return {
      rowIndex: offset + index,
      sampleId: review ? stringOrNull(sampleIds?.get(index)) : null,
      defectId: numeric(defectIds?.get(index)),
      reviewImages: review ? parseReviewImages(reviewImages?.get(index)) : EMPTY_REVIEW_IMAGES,
      annotationLabel: stringOrNull(annotationLabels?.get(index)),
      predictionLabel: stringOrNull(predictionLabels?.get(index)),
      predictionConfidence: confidence == null ? null : numeric(confidence),
    };
  });
}

const patchRequestedRange = ref({ start: 0, end: 1 });
const reviewRequestedRange = ref({ start: 0, end: 1 });
const patchGallery = usePagedPerspectiveGallery(
  computed(() => props.patchViewSnapshot ?? null),
  patchRequestedRange,
  (ipc, offset) => samplesFromArrow(ipc, offset, false),
  {
    onRecoverableError: (_reason, error) => {
      console.warn("[blink] patch view read failed", error);
    },
  },
);
const reviewGallery = usePagedPerspectiveGallery(
  computed(() => props.reviewViewSnapshot ?? null),
  reviewRequestedRange,
  (ipc, offset) => samplesFromArrow(ipc, offset, true),
  {
    onRecoverableError: (_reason, error) => {
      console.warn("[blink] review view read failed", error);
    },
  },
);

watch(
  () => props.patchSamplesPerRow,
  (v) => {
    const next = clampSamplesPerRow(v);
    if (patchPerRow.value !== next) patchPerRow.value = next;
  },
);
watch(
  () => props.reviewSamplesPerRow,
  (v) => {
    const next = clampSamplesPerRow(v);
    if (reviewPerRow.value !== next) reviewPerRow.value = next;
  },
);
watch(
  () => props.patchCellSize,
  (v) => {
    const next = normalizeImageSize(v);
    if (patchImageSize.value !== next) patchImageSize.value = next;
  },
);
watch(
  () => props.reviewCellSize,
  (v) => {
    const next = normalizeImageSize(v);
    if (reviewImageSize.value !== next) reviewImageSize.value = next;
  },
);
const samplesRef = computed(() =>
  mode.value === "review" ? reviewGallery.window.value.items : patchGallery.window.value.items,
);
const totalSamples = computed(() =>
  mode.value === "review" ? reviewGallery.window.value.total : patchGallery.window.value.total,
);
const sampleOffset = computed(() =>
  mode.value === "review" ? reviewGallery.window.value.offset : patchGallery.window.value.offset,
);
const currentLoading = computed(
  () =>
    (props.loading ||
      (mode.value === "review" ? reviewGallery.isPending.value : patchGallery.isPending.value)) &&
    samplesRef.value.length === 0,
);
const patchCellSizeRef = patchImageSize;
const reviewCellSizeRef = reviewImageSize;
const overscanRef = computed(() => props.overscan);
const PREDICTION_BADGE_ROW_HEIGHT = 26;
const extraRowHeight = computed(() =>
  props.showPredictionBadges ? PREDICTION_BADGE_ROW_HEIGHT : 0,
);
const {
  virtualizer,
  virtualRowHeightStr,
  shouldLoadImages,
  queueViewportImageLoad,
  scrollRef,
  visibleSamples,
  imageCellHeightPxStr,
  samplesForVirtualRow,
  effectiveSamplesPerRow,
} = useBlinkVirtualScroll({
  samples: samplesRef,
  mode,
  patchPerRow,
  reviewPerRow,
  patchCellSize: patchCellSizeRef,
  reviewCellSize: reviewCellSizeRef,
  extraRowHeight,
  overscan: overscanRef,
  totalSamples,
  sampleOffset,
  reviewSamplesArePreFiltered: true,
});

const virtualItems = computed(() => virtualizer.value.getVirtualItems());

watch(
  () => {
    const items = virtualItems.value;
    const firstRow = items[0]?.index ?? 0;
    const lastRow = items.at(-1)?.index ?? firstRow;
    const perRow = effectiveSamplesPerRow.value;
    return {
      mode: mode.value,
      start: firstRow * perRow,
      end: Math.min(totalSamples.value, (lastRow + 1) * perRow),
    };
  },
  ({ mode: activeMode, start, end }) => {
    const range = { start, end: Math.max(start + 1, end) };
    if (activeMode === "review") {
      reviewRequestedRange.value = range;
    } else {
      patchRequestedRange.value = range;
    }
  },
  { immediate: true },
);

const cellSize = computed(() =>
  mode.value === "patch" ? patchImageSize.value : reviewImageSize.value,
);

const {
  enabled: blinkEnabled,
  phase: blinkPhase,
  toggle: toggleBlink,
} = useBlinkController({
  intervalMs: props.blinkIntervalMs,
  initialEnabled: props.initialBlinkEnabled,
});

const selectedPatchImageTypes = computed<PatchImageType[]>(() => {
  const seen = new Set<PatchImageType>();
  const parsed = patchImagesInput.value
    .split(",")
    .map((part) => patchImageTypeByInput[part.trim().toLowerCase()])
    .filter((type): type is PatchImageType => !!type)
    .filter((type) => {
      if (seen.has(type)) return false;
      seen.add(type);
      return true;
    });
  return parsed;
});

function syncPatchSwitchesFromInput() {
  const types = selectedPatchImageTypes.value;
  patchDefectiveEnabled.value = types.includes("Defective");
  patchReferenceEnabled.value = types.includes("Reference");
  patchDifferenceEnabled.value = types.includes("Difference");
}

syncPatchSwitchesFromInput();

const discoveredReviewImageIds = ref<Set<number>>(new Set());
let reviewImageIdsView: PerspectiveViewSnapshot["view"]["rawView"] | null = null;

watch(
  [() => props.reviewViewSnapshot, () => reviewGallery.window.value],
  ([snapshot, galleryWindow]) => {
    const rawView = snapshot?.view.rawView ?? null;
    if (rawView !== reviewImageIdsView) {
      reviewImageIdsView = rawView;
      discoveredReviewImageIds.value = new Set();
    }
    if (!snapshot) return;
    const next = new Set(discoveredReviewImageIds.value);
    for (const sample of galleryWindow.items) {
      for (const imageId of sample.reviewImages) {
        if (Number.isInteger(imageId) && imageId > 0) next.add(imageId);
      }
    }
    discoveredReviewImageIds.value = next;
  },
  { immediate: true },
);

const inferredReviewImageIds = computed<number[]>(() => {
  return [...discoveredReviewImageIds.value].sort((a, b) => a - b);
});

watch(
  inferredReviewImageIds,
  (ids) => {
    if (!reviewImagesInputEdited.value) {
      reviewImagesInput.value = ids.join(",");
    }
  },
  { immediate: true },
);

const selectedReviewImageIds = computed<number[]>(() => {
  const seen = new Set<number>();
  const parsed = reviewImagesInput.value
    .split(",")
    .map((part) => Number(part.trim()))
    .filter((imageId) => Number.isInteger(imageId) && imageId > 0)
    .filter((imageId) => {
      if (seen.has(imageId)) return false;
      seen.add(imageId);
      return true;
    });
  return parsed;
});

const patchImageTypesForSprite = computed<PatchImageType[]>(() => {
  const requested = [...selectedPatchImageTypes.value];
  if (blinkEnabled.value) {
    for (const required of ["Reference", "Defective"] as PatchImageType[]) {
      if (!requested.includes(required)) requested.unshift(required);
    }
  }
  return requested;
});

const basePatchColumns = computed(() =>
  selectedPatchImageTypes.value
    .map((type) => ({
      label: PATCH_IMAGE_LABELS[type],
      spriteIndex: patchImageTypesForSprite.value.indexOf(type),
      type,
    }))
    .filter((column) => column.spriteIndex >= 0),
);

function reviewColumnsForSample(sample: BlinkSample): number[] {
  const available = new Set(sample.reviewImages);
  return selectedReviewImageIds.value.filter((imageId) => available.has(imageId));
}

function spriteImageTypesForSample(sample: BlinkSample): string[] {
  const imageTypes = patchImageTypesForSprite.value.map((type) => PATCH_IMAGE_SPRITE_TOKENS[type]);
  if (mode.value === "review") {
    for (const imageId of reviewColumnsForSample(sample)) {
      imageTypes.push(`review${imageId}`);
    }
  }
  return imageTypes;
}

function cellsForSample(sample: BlinkSample): number {
  const imageCells =
    basePatchColumns.value.length +
    (mode.value === "review" ? reviewColumnsForSample(sample).length : 0);
  return imageCells + (blinkEnabled.value ? 1 : 0);
}

const maxCellsPerSample = computed(
  () =>
    basePatchColumns.value.length +
    (mode.value === "review" ? selectedReviewImageIds.value.length : 0) +
    (blinkEnabled.value ? 1 : 0),
);

const SAMPLE_BLOCK_PADDING_X = 4;

function sampleBlockWidthPx(sample: BlinkSample): number {
  const cells = cellsForSample(sample);
  return cells * cellSize.value + Math.max(0, cells - 1) * props.cellGap + SAMPLE_BLOCK_PADDING_X;
}

const maxSampleBlockWidthPx = computed(
  () =>
    maxCellsPerSample.value * cellSize.value +
    Math.max(0, maxCellsPerSample.value - 1) * props.cellGap +
    SAMPLE_BLOCK_PADDING_X,
);

const rowMinWidthPx = computed(
  () =>
    effectiveSamplesPerRow.value * maxSampleBlockWidthPx.value +
    (effectiveSamplesPerRow.value - 1) * props.rowGap +
    24 /* left+right row padding */,
);
const cellSizePx = computed(() => `${cellSize.value}px`);
function sampleBlockWidthStr(sample: BlinkSample): string {
  return `${sampleBlockWidthPx(sample)}px`;
}
const rowMinWidthStr = computed(() => `${rowMinWidthPx.value}px`);

const { rubberBandStyle, onMouseDown } = useBlinkRubberBand({
  scrollRef,
  onSelect: (ids, mods) => emit("selectSamples", ids, mods),
});

const requestedSpriteUrls = ref<Set<string>>(new Set());

function isSelected(defectId: number | string): boolean {
  const idStr = defectIdKey(defectId);
  if (props.selectedDefectIds instanceof Set) {
    return props.selectedDefectIds.has(idStr);
  }
  return props.selectedDefectIds.includes(idStr);
}

function defectIdKey(defectId: number | string): string {
  return String(defectId);
}

const selectionAnchorRowIndex = ref<number | null>(null);

async function defectIdsBetween(start: number, end: number): Promise<string[]> {
  const rangeStart = Math.min(start, end);
  const rangeEnd = Math.max(start, end) + 1;
  const galleryWindow =
    mode.value === "review" ? reviewGallery.window.value : patchGallery.window.value;
  if (
    rangeStart >= galleryWindow.offset &&
    rangeEnd <= galleryWindow.offset + galleryWindow.items.length
  ) {
    return galleryWindow.items
      .slice(rangeStart - galleryWindow.offset, rangeEnd - galleryWindow.offset)
      .map((sample) => defectIdKey(sample.defectId));
  }

  const snapshot = mode.value === "review" ? props.reviewViewSnapshot : props.patchViewSnapshot;
  if (!snapshot) return [];
  const table = tableFromIPC(
    (await snapshot.view.to_arrow({
      start_row: rangeStart,
      end_row: rangeEnd,
    })) as Uint8Array,
  );
  const defectIds = table.getChild("defect_id");
  return Array.from({ length: table.numRows }, (_, index) =>
    defectIdKey(numeric(defectIds?.get(index))),
  );
}

async function handleSampleClick(sample: BlinkSample, event: MouseEvent): Promise<void> {
  const targetId = defectIdKey(sample.defectId);
  const ctrlOrMeta = event.ctrlKey || event.metaKey;
  if (event.shiftKey) {
    const anchorRowIndex = selectionAnchorRowIndex.value ?? sample.rowIndex;
    const ids = await defectIdsBetween(anchorRowIndex, sample.rowIndex);
    emit("selectSamples", ids.length > 0 ? ids : [targetId], {
      shift: true,
      ctrl: event.ctrlKey,
      meta: event.metaKey,
      selectionMode: ctrlOrMeta ? "add" : "replace",
    });
    return;
  }

  selectionAnchorRowIndex.value = sample.rowIndex;
  emit("selectSamples", [targetId], {
    shift: false,
    ctrl: event.ctrlKey,
    meta: event.metaKey,
    selectionMode: ctrlOrMeta ? "toggle" : "replace",
  });
}

const previewImageSrc = ref<string | null>(null);
const hiddenImageRef = ref<InstanceType<typeof NImage> | null>(null);

function handleReviewPreview(sample: BlinkSample, imageId: number) {
  if (!props.datasetId || !sample.sampleId) return;
  previewImageSrc.value = scSampleImageUrl(props.datasetId, sample.sampleId, imageId);
  void nextTick(() => {
    const el = hiddenImageRef.value?.$el;
    if (el instanceof HTMLElement) {
      el.click();
    }
  });
}

function getSpriteUrl(sample: BlinkSample): string {
  const isPatch = mode.value === "patch";
  const cs = isPatch ? patchImageSize.value : reviewImageSize.value;
  const params = new URLSearchParams();
  params.set("cell_size", String(cs));
  for (const type of spriteImageTypesForSample(sample)) {
    params.append("image_types", type);
  }
  const spriteMode = isPatch ? "patch" : "review";
  return `/api/v1/sc/sprites/${spriteMode}/${props.inspectionTime}/${props.waferKey}/${
    sample.defectId
  }?${params.toString()}`;
}

function shouldRenderSprite(sample: BlinkSample): boolean {
  const url = getSpriteUrl(sample);
  if (shouldLoadImages.value) {
    requestedSpriteUrls.value.add(url);
    return true;
  }
  return requestedSpriteUrls.value.has(url);
}

function getSpriteStyle(sample: BlinkSample, colIndex: number) {
  const cols = spriteImageTypesForSample(sample).length;
  const url = getSpriteUrl(sample);

  const bgSize = `${cols * cellSize.value}px ${cellSize.value}px`;
  const bgPos = `${-colIndex * cellSize.value}px 0`;

  return {
    backgroundImage: `url(${withAuthQueryParams(url)})`,
    backgroundSize: bgSize,
    backgroundPosition: bgPos,
    backgroundRepeat: "no-repeat",
  };
}

function blinkBaseSpriteIndex(): number {
  const referenceIndex = patchImageTypesForSprite.value.indexOf("Reference");
  return referenceIndex >= 0 ? referenceIndex : 0;
}

function blinkOverlaySpriteIndex(): number {
  const defectiveIndex = patchImageTypesForSprite.value.indexOf("Defective");
  return defectiveIndex >= 0 ? defectiveIndex : 0;
}

function reviewSpriteIndex(sample: BlinkSample, imageId: number): number {
  const selectedIndex = reviewColumnsForSample(sample).indexOf(imageId);
  return patchImageTypesForSprite.value.length + Math.max(0, selectedIndex);
}

interface ScrollMetrics {
  clientWidth: number;
  clientHeight: number;
  scrollWidth: number;
  scrollHeight: number;
  scrollLeft: number;
  scrollTop: number;
}

const MIN_SCROLL_THUMB_SIZE = 24;
const scrollMetrics = ref<ScrollMetrics>({
  clientWidth: 0,
  clientHeight: 0,
  scrollWidth: 0,
  scrollHeight: 0,
  scrollLeft: 0,
  scrollTop: 0,
});
let resizeObserver: ResizeObserver | null = null;
let dragState: {
  axis: "x" | "y";
  startPointer: number;
  startScroll: number;
  scrollableDistance: number;
  trackDistance: number;
} | null = null;

const showYScrollbar = computed(
  () => scrollMetrics.value.scrollHeight > scrollMetrics.value.clientHeight + 1,
);
const showXScrollbar = computed(
  () => scrollMetrics.value.scrollWidth > scrollMetrics.value.clientWidth + 1,
);

const yThumbSize = computed(() => {
  const { clientHeight, scrollHeight } = scrollMetrics.value;
  if (clientHeight <= 0 || scrollHeight <= 0) return 0;
  return Math.min(
    clientHeight,
    Math.max(MIN_SCROLL_THUMB_SIZE, (clientHeight / scrollHeight) * clientHeight),
  );
});

const xThumbSize = computed(() => {
  const { clientWidth, scrollWidth } = scrollMetrics.value;
  if (clientWidth <= 0 || scrollWidth <= 0) return 0;
  return Math.min(
    clientWidth,
    Math.max(MIN_SCROLL_THUMB_SIZE, (clientWidth / scrollWidth) * clientWidth),
  );
});

const yThumbOffset = computed(() => {
  const { clientHeight, scrollHeight, scrollTop } = scrollMetrics.value;
  const scrollableDistance = scrollHeight - clientHeight;
  const trackDistance = clientHeight - yThumbSize.value;
  if (scrollableDistance <= 0 || trackDistance <= 0) return 0;
  return (scrollTop / scrollableDistance) * trackDistance;
});

const xThumbOffset = computed(() => {
  const { clientWidth, scrollWidth, scrollLeft } = scrollMetrics.value;
  const scrollableDistance = scrollWidth - clientWidth;
  const trackDistance = clientWidth - xThumbSize.value;
  if (scrollableDistance <= 0 || trackDistance <= 0) return 0;
  return (scrollLeft / scrollableDistance) * trackDistance;
});

const yThumbStyle = computed<CSSProperties>(() => ({
  height: `${yThumbSize.value}px`,
  transform: `translateY(${yThumbOffset.value}px)`,
}));

const xThumbStyle = computed<CSSProperties>(() => ({
  width: `${xThumbSize.value}px`,
  transform: `translateX(${xThumbOffset.value}px)`,
}));

function syncScrollMetrics(): void {
  const element = scrollRef.value;
  if (!element) return;
  scrollMetrics.value = {
    clientWidth: element.clientWidth,
    clientHeight: element.clientHeight,
    scrollWidth: element.scrollWidth,
    scrollHeight: element.scrollHeight,
    scrollLeft: element.scrollLeft,
    scrollTop: element.scrollTop,
  };
}

function attachResizeObserver(element: HTMLElement | null): void {
  resizeObserver?.disconnect();
  resizeObserver = null;
  if (!element || typeof ResizeObserver === "undefined") return;
  resizeObserver = new ResizeObserver(() => syncScrollMetrics());
  resizeObserver.observe(element);
  const content = element.firstElementChild;
  if (content instanceof HTMLElement) {
    resizeObserver.observe(content);
  }
}

watch(
  scrollRef,
  (element) => {
    attachResizeObserver(element);
    void nextTick(syncScrollMetrics);
  },
  { flush: "post" },
);

watch(
  [
    () => visibleSamples.value.length,
    rowMinWidthPx,
    virtualRowHeightStr,
    imageSize,
    selectedPatchImageTypes,
    selectedReviewImageIds,
    blinkEnabled,
  ],
  () => {
    void nextTick(syncScrollMetrics);
  },
  { flush: "post" },
);

function handleScroll(): void {
  queueViewportImageLoad();
  syncScrollMetrics();
}

function beginScrollbarDrag(axis: "x" | "y", event: MouseEvent): void {
  const element = scrollRef.value;
  if (!element) return;
  const metrics = scrollMetrics.value;
  const scrollableDistance =
    axis === "y"
      ? metrics.scrollHeight - metrics.clientHeight
      : metrics.scrollWidth - metrics.clientWidth;
  const trackDistance =
    axis === "y" ? metrics.clientHeight - yThumbSize.value : metrics.clientWidth - xThumbSize.value;
  if (scrollableDistance <= 0 || trackDistance <= 0) return;
  dragState = {
    axis,
    startPointer: axis === "y" ? event.clientY : event.clientX,
    startScroll: axis === "y" ? element.scrollTop : element.scrollLeft,
    scrollableDistance,
    trackDistance,
  };
  document.addEventListener("mousemove", handleScrollbarDrag);
  document.addEventListener("mouseup", endScrollbarDrag, { once: true });
}

function handleScrollbarDrag(event: MouseEvent): void {
  const element = scrollRef.value;
  if (!element || !dragState) return;
  const pointer = dragState.axis === "y" ? event.clientY : event.clientX;
  const delta = pointer - dragState.startPointer;
  const scrollDelta = (delta / dragState.trackDistance) * dragState.scrollableDistance;
  if (dragState.axis === "y") {
    element.scrollTop = dragState.startScroll + scrollDelta;
  } else {
    element.scrollLeft = dragState.startScroll + scrollDelta;
  }
  syncScrollMetrics();
}

function endScrollbarDrag(): void {
  dragState = null;
  document.removeEventListener("mousemove", handleScrollbarDrag);
}

function jumpScrollbar(axis: "x" | "y", event: MouseEvent): void {
  const element = scrollRef.value;
  if (!element) return;
  const target = event.currentTarget;
  if (!(target instanceof HTMLElement)) return;
  const rect = target.getBoundingClientRect();
  if (axis === "y") {
    const offset = event.clientY - rect.top - yThumbSize.value / 2;
    const trackDistance = scrollMetrics.value.clientHeight - yThumbSize.value;
    if (trackDistance > 0) {
      element.scrollTop =
        (offset / trackDistance) *
        (scrollMetrics.value.scrollHeight - scrollMetrics.value.clientHeight);
    }
  } else {
    const offset = event.clientX - rect.left - xThumbSize.value / 2;
    const trackDistance = scrollMetrics.value.clientWidth - xThumbSize.value;
    if (trackDistance > 0) {
      element.scrollLeft =
        (offset / trackDistance) *
        (scrollMetrics.value.scrollWidth - scrollMetrics.value.clientWidth);
    }
  }
  syncScrollMetrics();
}

const SETTINGS_STORAGE_KEY = "blink-table-settings";

interface PersistedSettings {
  blinkEnabled?: boolean;
  showDefectIdLabel?: boolean;
  patchPerRow?: number;
  reviewPerRow?: number;
  patchImageSize?: number;
  reviewImageSize?: number;
  patchImagesInput?: string;
}

function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return;
    const saved: PersistedSettings = JSON.parse(raw);
    if (typeof saved.blinkEnabled === "boolean" && blinkEnabled.value !== saved.blinkEnabled) {
      toggleBlink();
    }
    if (typeof saved.showDefectIdLabel === "boolean")
      showDefectIdLabel.value = saved.showDefectIdLabel;
    if (typeof saved.patchPerRow === "number")
      patchPerRow.value = clampSamplesPerRow(saved.patchPerRow);
    if (typeof saved.reviewPerRow === "number")
      reviewPerRow.value = clampSamplesPerRow(saved.reviewPerRow);
    if (typeof saved.patchImageSize === "number")
      patchImageSize.value = normalizeImageSize(saved.patchImageSize);
    if (typeof saved.reviewImageSize === "number")
      reviewImageSize.value = normalizeImageSize(saved.reviewImageSize);
    if (typeof saved.patchImagesInput === "string") patchImagesInput.value = saved.patchImagesInput;
    syncPatchSwitchesFromInput();
  } catch {
    /* ignore */
  }
}

function saveSettings() {
  const data: PersistedSettings = {
    blinkEnabled: blinkEnabled.value,
    showDefectIdLabel: showDefectIdLabel.value,
    patchPerRow: patchPerRow.value,
    reviewPerRow: reviewPerRow.value,
    patchImageSize: patchImageSize.value,
    reviewImageSize: reviewImageSize.value,
    patchImagesInput: patchImagesInput.value,
  };
  try {
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(data));
  } catch {
    /* ignore */
  }
}

onMounted(() => {
  loadSettings();
  window.addEventListener("resize", syncScrollMetrics);
  void nextTick(syncScrollMetrics);
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  document.removeEventListener("mousemove", handleScrollbarDrag);
  window.removeEventListener("resize", syncScrollMetrics);
});

watch(settingsOpen, (open) => {
  if (!open) saveSettings();
});

defineExpose({ scrollRef });
</script>

<template>
  <div
    class="sbt"
    :data-loaded-samples="samplesRef.length"
    :data-sample-offset="sampleOffset"
    :data-total-samples="totalSamples"
  >
    <!-- Toolbar -->
    <div class="sbt-toolbar">
      <div class="sbt-toolbar-left">
        <n-radio-group
          v-if="showModeSwitch"
          v-model:value="mode"
          size="small"
          class="sbt-mode-radio"
        >
          <n-radio-button value="patch">Patch</n-radio-button>
          <n-radio-button value="review">Review</n-radio-button>
        </n-radio-group>

        <n-text v-if="currentLoading" depth="3" class="sbt-review-status"> Loading... </n-text>
        <n-button size="tiny" quaternary @click="settingsOpen = true"> Settings </n-button>
      </div>
      <div class="sbt-toolbar-right">
        <n-text class="sbt-row-count" depth="3">
          {{ totalSamples.toLocaleString() }} samples
        </n-text>
      </div>
    </div>

    <n-modal
      v-model:show="settingsOpen"
      preset="card"
      title="Table Settings"
      class="sbt-settings-modal"
      :style="{ width: '380px' }"
    >
      <div class="sbt-settings">
        <div class="sbt-setting-row">
          <n-text class="sbt-control-label">Per Row</n-text>
          <div class="sbt-per-row">
            <n-button
              size="tiny"
              quaternary
              class="sbt-per-row-button"
              aria-label="Decrease samples per row"
              :disabled="samplesPerRow <= 1"
              @click="adjustSamplesPerRow(-1)"
            >
              &minus;
            </n-button>
            <n-text class="sbt-per-row-value" aria-live="polite">
              {{ samplesPerRow }}
            </n-text>
            <n-button
              size="tiny"
              quaternary
              class="sbt-per-row-button"
              aria-label="Increase samples per row"
              :disabled="samplesPerRow >= MAX_SAMPLES_PER_ROW"
              @click="adjustSamplesPerRow(1)"
            >
              +
            </n-button>
          </div>
        </div>

        <div class="sbt-setting-row">
          <n-text class="sbt-control-label">Size</n-text>
          <n-select
            v-model:value="imageSize"
            size="small"
            class="sbt-size-select"
            :options="IMAGE_SIZE_SELECT_OPTIONS"
            :consistent-menu-width="false"
          />
        </div>

        <div class="sbt-setting-block">
          <n-text class="sbt-control-label">Patch Image</n-text>
          <div class="sbt-setting-row">
            <n-text class="sbt-control-label">Blink</n-text>
            <n-switch :value="blinkEnabled" size="small" @update:value="toggleBlink" />
          </div>
          <div class="sbt-setting-row">
            <n-text class="sbt-control-label">ID Label</n-text>
            <n-switch v-model:value="showDefectIdLabel" size="small" />
          </div>
          <div class="sbt-setting-row">
            <n-text class="sbt-control-label">Defective</n-text>
            <n-switch
              :value="patchDefectiveEnabled"
              size="small"
              @update:value="
                patchDefectiveEnabled = $event;
                rebuildPatchImagesInput();
              "
            />
          </div>
          <div class="sbt-setting-row">
            <n-text class="sbt-control-label">Reference</n-text>
            <n-switch
              :value="patchReferenceEnabled"
              size="small"
              @update:value="
                patchReferenceEnabled = $event;
                rebuildPatchImagesInput();
              "
            />
          </div>
          <div class="sbt-setting-row">
            <n-text class="sbt-control-label">Difference</n-text>
            <n-switch
              :value="patchDifferenceEnabled"
              size="small"
              @update:value="
                patchDifferenceEnabled = $event;
                rebuildPatchImagesInput();
              "
            />
          </div>
        </div>

        <div class="sbt-setting-block">
          <n-text class="sbt-control-label">Review Images</n-text>
          <n-input
            v-model:value="reviewImagesInput"
            size="small"
            placeholder="Inferred from review images"
            @update:value="reviewImagesInputEdited = true"
          />
        </div>
      </div>
    </n-modal>

    <NImage
      ref="hiddenImageRef"
      :src="previewImageSrc || ''"
      :style="{ position: 'fixed', top: '-9999px', left: '-9999px', width: '1px', height: '1px' }"
    />

    <!-- Empty state -->
    <div v-if="totalSamples === 0" class="sbt-empty">
      <n-text depth="3">
        {{ mode === "review" ? "No samples with review images" : "No rows to display" }}
      </n-text>
    </div>

    <!-- Scroll body -->
    <div v-else class="sbt-scroll-shell" data-testid="blink-table-scrollbar">
      <div ref="scrollRef" class="sbt-scroll" @scroll="handleScroll" @mousedown="onMouseDown">
        <div
          class="sbt-vrow"
          :style="{ height: virtualizer.getTotalSize() + 'px', position: 'relative' }"
        >
          <div class="sbt-rubber-band" :style="rubberBandStyle"></div>
          <div
            v-for="virtualRow in virtualItems"
            :key="virtualRow.index"
            class="sbt-row-wrapper"
            :class="{ 'sbt-vrow--odd': virtualRow.index % 2 === 1 }"
            :style="{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: virtualRowHeightStr,
              transform: `translateY(${virtualRow.start}px)`,
            }"
          >
            <div class="sbt-row" :style="{ minWidth: rowMinWidthStr }">
              <div
                v-for="sample in samplesForVirtualRow(virtualRow.index)"
                :key="sample.defectId"
                class="sbt-sample-block"
                :class="{ 'sbt-sample-block--selected': isSelected(sample.defectId) }"
                :data-defect-id="sample.defectId"
                :style="{ width: sampleBlockWidthStr(sample) }"
                @click.stop="handleSampleClick(sample, $event)"
              >
                <!-- Mini Header -->
                <div class="sbt-sample-mini-header">
                  <div v-if="blinkEnabled" class="sbt-sample-header-label">Blink</div>
                  <div
                    v-for="col in basePatchColumns"
                    :key="'base_header_' + col.spriteIndex"
                    class="sbt-sample-header-label"
                  >
                    {{ col.label }}
                  </div>
                  <template v-if="mode === 'review'">
                    <div
                      v-for="imageId in reviewColumnsForSample(sample)"
                      :key="'rev_header_' + imageId"
                      class="sbt-sample-header-label"
                    >
                      Rev {{ imageId }}
                    </div>
                  </template>
                </div>

                <!-- Images Row -->
                <div class="sbt-sample-images-row" :style="{ height: imageCellHeightPxStr }">
                  <!-- Blink Cell -->
                  <div v-if="blinkEnabled" class="sbt-img-cell">
                    <template v-if="shouldRenderSprite(sample)">
                      <!-- Base reference layer -->
                      <div
                        class="sbt-sprite-layer"
                        :style="getSpriteStyle(sample, blinkBaseSpriteIndex())"
                      ></div>
                      <!-- Defective overlay layer -->
                      <div
                        class="sbt-sprite-layer sbt-overlay"
                        :class="{ 'is-active': blinkPhase === 'B' }"
                        :style="getSpriteStyle(sample, blinkOverlaySpriteIndex())"
                      ></div>
                    </template>
                    <div v-else class="sbt-img-placeholder"></div>
                    <div v-if="showDefectIdLabel" class="sbt-defect-id">{{ sample.defectId }}</div>
                  </div>

                  <!-- Base patch cells -->
                  <div
                    v-for="(col, colIdx) in basePatchColumns"
                    :key="'base_' + col.spriteIndex"
                    class="sbt-img-cell"
                  >
                    <div
                      v-if="shouldRenderSprite(sample)"
                      class="sbt-sprite-layer"
                      :style="getSpriteStyle(sample, col.spriteIndex)"
                    ></div>
                    <div v-else class="sbt-img-placeholder"></div>
                    <div
                      v-if="showDefectIdLabel && !blinkEnabled && colIdx === 0"
                      class="sbt-defect-id"
                    >
                      {{ sample.defectId }}
                    </div>
                  </div>

                  <!-- Review Cells -->
                  <template v-if="mode === 'review'">
                    <div
                      v-for="imageId in reviewColumnsForSample(sample)"
                      :key="'rev_' + imageId"
                      class="sbt-img-cell sbt-img-cell--preview"
                      @click.stop="handleReviewPreview(sample, imageId)"
                    >
                      <div
                        v-if="shouldRenderSprite(sample)"
                        class="sbt-sprite-layer"
                        :style="getSpriteStyle(sample, reviewSpriteIndex(sample, imageId))"
                      ></div>
                      <div v-else class="sbt-img-placeholder"></div>
                    </div>
                  </template>
                </div>

                <!-- Prediction / Annotation / Draft Badges -->
                <div v-if="showPredictionBadges" class="sbt-prediction-row">
                  <n-tag
                    v-if="annotationDrafts[defectIdKey(sample.defectId)]"
                    type="warning"
                    size="small"
                    class="sbt-prediction-badge"
                    title="Draft (unsubmitted)"
                  >
                    D: {{ annotationDrafts[defectIdKey(sample.defectId)] }}
                  </n-tag>
                  <n-tag
                    v-if="sample.annotationLabel"
                    type="success"
                    size="small"
                    class="sbt-prediction-badge"
                    title="Annotation (saved)"
                  >
                    A: {{ sample.annotationLabel }}
                  </n-tag>
                  <n-tag
                    v-if="sample.predictionLabel"
                    type="info"
                    size="small"
                    class="sbt-prediction-badge"
                    title="Latest prediction"
                  >
                    P: {{ sample.predictionLabel
                    }}{{
                      sample.predictionConfidence != null
                        ? ` (${(sample.predictionConfidence * 100).toFixed(0)}%)`
                        : ""
                    }}
                  </n-tag>
                  <div v-else></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div
        v-if="showYScrollbar"
        class="sbt-scrollbar-rail sbt-scrollbar-rail--y"
        @mousedown.prevent="jumpScrollbar('y', $event)"
      >
        <div
          class="sbt-scrollbar-thumb"
          :style="yThumbStyle"
          @mousedown.stop.prevent="beginScrollbarDrag('y', $event)"
        ></div>
      </div>
      <div
        v-if="showXScrollbar"
        class="sbt-scrollbar-rail sbt-scrollbar-rail--x"
        @mousedown.prevent="jumpScrollbar('x', $event)"
      >
        <div
          class="sbt-scrollbar-thumb"
          :style="xThumbStyle"
          @mousedown.stop.prevent="beginScrollbarDrag('x', $event)"
        ></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sbt {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  background: var(--cv-card-bg, #1e1e2e);
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  border-radius: 8px;
  overflow: hidden;
}

/* Toolbar */
.sbt-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  background: color-mix(in srgb, var(--cv-card-bg, #1e1e2e) 50%, var(--cv-bg, #16162a));
  flex-shrink: 0;
}

.sbt-toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.sbt-toolbar-right {
  display: flex;
  align-items: center;
}

.sbt-blink-label {
  font-size: 13px;
  font-weight: 500;
}

.sbt-row-count {
  font-size: 12px;
}

.sbt-mode-radio {
  margin-left: 6px;
}

.sbt-per-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sbt-per-row-label {
  font-size: 11px;
  white-space: nowrap;
}

.sbt-per-row-button {
  width: 22px;
  min-width: 22px;
  padding: 0;
}

.sbt-per-row-value {
  min-width: 24px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  text-align: center;
}

.sbt-review-status {
  font-size: 12px;
}

.sbt-control {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sbt-control-label {
  font-size: 11px;
  white-space: nowrap;
}

.sbt-size-select {
  width: 72px;
}

.sbt-settings {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.sbt-setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.sbt-setting-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Scroll body */
.sbt-scroll-shell {
  flex: 1;
  min-height: 0;
  position: relative;
  user-select: none;
  overflow: hidden;
}

.sbt-scroll {
  width: 100%;
  height: 100%;
  overflow: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.sbt-scroll::-webkit-scrollbar {
  width: 0;
  height: 0;
}

.sbt-scrollbar-rail {
  position: absolute;
  z-index: 20;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.28);
  user-select: none;
}

.sbt-scrollbar-rail--y {
  top: 0;
  right: 0;
  bottom: 0;
  width: 10px;
}

.sbt-scrollbar-rail--x {
  right: 0;
  bottom: 0;
  left: 0;
  height: 10px;
}

.sbt-scrollbar-thumb {
  width: 100%;
  height: 100%;
  border-radius: 999px;
  background: rgba(142, 160, 255, 0.7);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.16);
  cursor: pointer;
}

.sbt-scrollbar-thumb:hover {
  background: rgba(142, 160, 255, 0.9);
}

/* Virtual row wrapper */
.sbt-vrow {
  box-sizing: border-box;
}

.sbt-vrow--odd .sbt-row {
  background: color-mix(in srgb, var(--cv-card-bg, #1e1e2e) 60%, var(--cv-bg, #16162a));
}

/* Row (horizontal flex of sample blocks) */
.sbt-row {
  display: flex;
  align-items: stretch;
  padding: v-bind("ROW_PADDING_Y + 'px'") 12px;
  gap: 12px;
  height: 100%;
  box-sizing: border-box;
}

/* Sample block */
.sbt-sample-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 0 0 auto;
  border-radius: 4px;
  padding: 2px;
  box-sizing: border-box;
  transition:
    background-color 0.15s,
    box-shadow 0.15s;
}

.sbt-sample-block--selected {
  background: color-mix(in srgb, var(--cv-primary, #4098fc) 12%, transparent);
  box-shadow: inset 0 0 0 2px var(--cv-primary, #4098fc);
}

/* Mini-header */
.sbt-sample-mini-header {
  display: flex;
  gap: 4px;
  height: v-bind("MINI_HEADER_HEIGHT + 'px'");
  align-items: center;
  padding: 0 2px;
}

.sbt-sample-header-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
  text-transform: uppercase;
  letter-spacing: 0.3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: center;
  flex-shrink: 0;
  width: v-bind("cellSizePx");
}

/* Images row */
.sbt-sample-images-row {
  display: flex;
  gap: 4px;
  box-sizing: border-box;
}

/* Image cell — fixed square, preserve 1:1 aspect ratio */
.sbt-img-cell {
  position: relative;
  width: v-bind("cellSizePx");
  height: v-bind("cellSizePx");
  overflow: hidden;
  background: #111;
  flex-shrink: 0;
}

.sbt-img-cell--preview {
  cursor: zoom-in;
}

.sbt-review-image {
  display: block;
  width: 100%;
  height: 100%;
}

.sbt-review-image :deep(img) {
  display: block;
}

.sbt-sprite-layer {
  width: 100%;
  height: 100%;
}

.sbt-img-placeholder {
  width: 100%;
  height: 100%;
  background: rgba(255, 255, 255, 0.04);
}

/* Rubber band selection overlay */
.sbt-rubber-band {
  position: absolute;
  border: 2px dashed var(--cv-primary, #4098fc);
  background: color-mix(in srgb, var(--cv-primary, #4098fc) 15%, transparent);
  pointer-events: none;
  z-index: 10;
}

/* Empty state */
.sbt-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 200px;
}

/* Overlay toggle */
.sbt-overlay {
  position: absolute;
  top: 0;
  left: 0;
  opacity: 0;
}

.sbt-overlay.is-active {
  opacity: 1;
}

/* Defect ID label */
.sbt-defect-id {
  position: absolute;
  bottom: 2px;
  left: 2px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.7);
  background: rgba(0, 0, 0, 0.55);
  padding: 1px 4px;
  border-radius: 2px;
  line-height: 1.2;
  max-width: calc(100% - 4px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  pointer-events: none;
}

/* Prediction / Annotation / Draft badge row */
.sbt-prediction-row {
  height: 26px;
  padding: 2px;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 4px;
  box-sizing: border-box;
  overflow: hidden;
}

.sbt-prediction-badge {
  font-size: 10px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
