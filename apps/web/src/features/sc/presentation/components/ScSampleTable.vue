<!--
  ScSampleTable — SC-specific virtualized sample data table.
  Uses virtual-window page loading (1k per page), so large inspection tables can
  jump directly to any offset without rendering placeholder defaults.
-->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useVirtualizer } from "@tanstack/vue-virtual";
import { NEmpty, NSpin, NText } from "naive-ui";
import type { ScSampleItem } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import {
  getInspectionSampleTableRowsApiV1ScInspectionsInspectionTimeWaferKeySampleTableRowsPost,
} from "@/generated/orval/endpoints/api";
import type { ScSampleTableRow } from "@/generated/orval/models/scSampleTableRow";

const props = defineProps<{
  /** @deprecated Use defectIds plus inspection identity. */
  samples?: ScSampleItem[];
  defectIds?: string[];
  inspectionTime?: string;
  waferKey?: number;
  loading: boolean;
  total: number;
}>();

// ── Column definitions ───────────────────────────
interface SampleRow {
  defectId: string;
  waferX: number | undefined;
  waferY: number | undefined;
  roughBin: number | undefined;
  classNumber: number | undefined;
  testId: number | undefined;
}

interface SampleColumn {
  key: string;
  title: string;
  width: number;
  render?: (row: SampleRow) => string;
}

const columns: SampleColumn[] = [
  { key: "defectId", title: "Defect ID", width: 180 },
  {
    key: "classNumber",
    title: "Class Number",
    width: 120,
    render(row) {
      return row.classNumber !== undefined ? String(row.classNumber) : "\u2014";
    },
  },
  {
    key: "testId",
    title: "Test ID",
    width: 100,
    render(row) {
      return row.testId !== undefined ? String(row.testId) : "\u2014";
    },
  },
  {
    key: "roughBin",
    title: "Rough Bin",
    width: 100,
    render(row) {
      return row.roughBin !== undefined ? String(row.roughBin) : "\u2014";
    },
  },
];

const resolvedDefectIds = computed(() =>
  props.defectIds ?? (props.samples ?? []).map((sample) => String(sample.defectId)),
);

const PAGE_SIZE = 1000;

// ── Sparse page cache keyed by the virtual row window ─────

const queryEnabled = computed(
  () =>
    !!props.inspectionTime &&
    props.waferKey !== undefined &&
    resolvedDefectIds.value.length > 0,
);

const tableQueryKey = computed(() =>
  [
    "sc",
    "sample-table-rows",
    props.inspectionTime,
    props.waferKey,
    resolvedDefectIds.value.length,
    resolvedDefectIds.value[0],
    resolvedDefectIds.value[resolvedDefectIds.value.length - 1],
  ].join(":"),
);

const loadedTotal = computed(() => resolvedDefectIds.value.length);

const rowsByDefectId = ref<Record<string, ScSampleTableRow>>({});
const loadedPageIndexes = ref<Set<number>>(new Set());
const loadingPageIndexes = ref<Set<number>>(new Set());
const pageError = ref<string | null>(null);

const loadedRowCount = computed(() => Object.keys(rowsByDefectId.value).length);
const hasMore = computed(() => loadedRowCount.value < loadedTotal.value);
const isFetching = computed(() => loadingPageIndexes.value.size > 0);

function setLoadingPage(page: number, loading: boolean): void {
  const next = new Set(loadingPageIndexes.value);
  if (loading) next.add(page);
  else next.delete(page);
  loadingPageIndexes.value = next;
}

async function fetchPage(page: number): Promise<void> {
  if (!queryEnabled.value) return;
  if (loadedPageIndexes.value.has(page) || loadingPageIndexes.value.has(page))
    return;

  const start = page * PAGE_SIZE;
  const slice = resolvedDefectIds.value.slice(start, start + PAGE_SIZE);
  if (slice.length === 0) return;

  setLoadingPage(page, true);
  pageError.value = null;
  try {
    const { data } =
      await getInspectionSampleTableRowsApiV1ScInspectionsInspectionTimeWaferKeySampleTableRowsPost(
        props.inspectionTime!,
        props.waferKey!,
        {
          defect_ids: slice,
          page: 0,
          page_size: PAGE_SIZE,
        },
      );
    if (!data || !("items" in data))
      throw new Error("Invalid sample table response");

    const nextRows = { ...rowsByDefectId.value };
    for (const row of data.items) {
      nextRows[row.defect_id] = row;
    }
    rowsByDefectId.value = nextRows;
    loadedPageIndexes.value = new Set([...loadedPageIndexes.value, page]);
  } catch (err) {
    pageError.value =
      err instanceof Error ? err.message : "Failed to load sample table rows";
  } finally {
    setLoadingPage(page, false);
  }
}

// ── Row accessor ──────────────────────────────────
function getRow(index: number): SampleRow {
  const defectId = resolvedDefectIds.value[index] ?? "";
  const row = rowsByDefectId.value[defectId];
  return {
    defectId,
    waferX: undefined,
    waferY: undefined,
    roughBin: row?.rough_bin ?? undefined,
    classNumber: row?.class_number ?? undefined,
    testId: row?.test_id ?? undefined,
  };
}

function cellValue(row: SampleRow, colKey: string): string {
  const col = columns.find((c) => c.key === colKey);
  if (col?.render) return col.render(row);
  return String((row as unknown as Record<string, unknown>)[colKey] ?? "");
}

// ── Virtualizer ───────────────────────────────────
const tableRef = ref<HTMLElement | null>(null);
const ROW_HEIGHT = 36;
const ROW_OVERSCAN = 16;

const virtualizer = useVirtualizer({
  get count() {
    return resolvedDefectIds.value.length;
  },
  getScrollElement: () => tableRef.value,
  estimateSize: () => ROW_HEIGHT,
  overscan: ROW_OVERSCAN,
});

function fetchPagesForVirtualRows(): void {
  const pages = new Set<number>();
  for (const item of virtualizer.value.getVirtualItems()) {
    pages.add(Math.floor(item.index / PAGE_SIZE));
  }
  for (const page of pages) {
    void fetchPage(page);
  }
}

watch(
  tableQueryKey,
  () => {
    rowsByDefectId.value = {};
    loadedPageIndexes.value = new Set();
    loadingPageIndexes.value = new Set();
    pageError.value = null;
    if (queryEnabled.value) void fetchPage(0);
    virtualizer.value.scrollToIndex(0);
  },
  { immediate: true },
);

watch(
  () => virtualizer.value.getVirtualItems().map((item) => item.index).join(","),
  () => fetchPagesForVirtualRows(),
);

const initialLoading = computed(
  () =>
    props.inspectionTime !== undefined &&
    props.waferKey !== undefined &&
    resolvedDefectIds.value.length > 0 &&
    loadedRowCount.value === 0 &&
    isFetching.value,
);

const queryError = computed(() => pageError.value);
</script>

<template>
  <div class="sst">
    <div class="sst-header">
      <NText depth="2" class="sst-header-label">
        Sample Data ({{ total }})
      </NText>
      <NText v-if="loadedTotal > 0" depth="3" class="sst-loaded-info">
        {{ loadedRowCount }} / {{ loadedTotal }} loaded
      </NText>
    </div>
    <div ref="tableRef" class="sst-scroll" @scroll="fetchPagesForVirtualRows">
      <NSpin :show="loading || initialLoading">
        <!-- Column headers (sticky) -->
        <div class="sst-col-headers">
          <span
            v-for="col in columns"
            :key="col.key"
            :style="{
              width: col.width + 'px',
              flexShrink: 0,
              padding: '4px 8px',
              fontWeight: 600,
              fontSize: '12px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }"
          >{{ col.title }}</span>
        </div>
        <!-- Virtual body -->
        <div
          :style="{
            height: virtualizer.getTotalSize() + 'px',
            position: 'relative',
          }"
        >
          <div
            v-for="vRow in virtualizer.getVirtualItems()"
            :key="String(vRow.key)"
            :style="{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: ROW_HEIGHT + 'px',
              transform: `translateY(${vRow.start}px)`,
              display: 'flex',
              alignItems: 'center',
              borderBottom: '1px solid var(--n-border-color, #333)',
            }"
            :class="{ 'sst-row--odd': vRow.index % 2 === 1 }"
          >
            <span
              v-for="col in columns"
              :key="col.key"
              :style="{
                width: col.width + 'px',
                flexShrink: 0,
                padding: '0 8px',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }"
            >{{ cellValue(getRow(vRow.index), col.key) }}</span>
          </div>
        </div>
        <!-- Empty state -->
        <NEmpty
          v-if="!initialLoading && !loading && resolvedDefectIds.length === 0"
          description="No samples"
          style="padding: 32px 0;"
        />
      </NSpin>
    </div>

    <div v-if="isFetching || hasMore" class="sst-footer">
      <NSpin v-if="isFetching" size="small" />
      <NText depth="3" style="font-size: 11px;">
        {{ isFetching ? "Loading visible rows..." : "Scroll to load rows" }}
      </NText>
    </div>

    <!-- Error -->
    <NText v-if="queryError" type="error" class="sst-error">{{ queryError }}</NText>
  </div>
</template>

<style scoped>
.sst {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--cv-card-bg, #1a1a2e);
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  padding: 8px 10px;
}

.sst-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  flex-shrink: 0;
}

.sst-header-label {
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.sst-loaded-info {
  font-size: 11px;
}

.sst-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.sst-col-headers {
  display: flex;
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--n-color, #1a1a1a);
  border-bottom: 2px solid var(--n-border-color, #555);
}

.sst-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 0 4px;
  flex-shrink: 0;
}

.sst-error {
  margin-top: 4px;
  font-size: 12px;
}
</style>
