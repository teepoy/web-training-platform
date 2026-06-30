<template>
  <div class="vxe-sandbox">
    <div class="vxe-sandbox-toolbar">
      <NSpace align="center" :wrap="true">
        <NText strong>Total Rows:</NText>
        <NInputNumber
          v-model:value="demoTotal"
          :disabled="loading"
          :min="0"
          :max="1_000_000"
          :step="1000"
          style="width: 180px"
          @update:value="rebuildTable"
        />
        <NDivider vertical />
        <NText depth="3">{{ statusText }}</NText>
      </NSpace>
    </div>

    <div class="vxe-sandbox-table">
      <ScSampleTableVxe
        v-if="table"
        :table="table"
        :view-config="viewConfig"
        :source-version="sourceVersion"
        @selection-change="handleSelectionChange"
      />
    </div>

    <div class="vxe-sandbox-footer">
      <NSpace>
        <NText depth="3">Log:</NText>
        <NText v-if="lastAction" depth="2">{{ lastAction }}</NText>
      </NSpace>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { NDivider, NInputNumber, NSpace, NText } from "naive-ui";
import perspective from "@perspective-dev/client";
import type { Client, Table, ViewConfigUpdate } from "@perspective-dev/client";
import clientWasmUrl from "@perspective-dev/client/dist/wasm/perspective-js.wasm?url";
import serverWasmUrl from "@perspective-dev/server/dist/wasm/perspective-server.wasm?url";
import ScSampleTableVxe from "@/features/sc/presentation/components/ScSampleTableVxe.vue";

const CHUNK_SIZE = 50_000;
const viewConfig: ViewConfigUpdate = {};

const demoTotal = ref(500);
const table = ref<Table | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const lastAction = ref("");
const sourceVersion = ref(0);
let client: Client | null = null;
let rebuildSeq = 0;

const statusText = computed(() => {
  if (error.value) return error.value;
  if (loading.value) return "Building Perspective worker table...";
  return "Perspective worker table -> ScSampleTableVxe, infinite virtual append, no pager.";
});

function rowChunk(startIndex: number, endIndex: number): Record<string, number[]> {
  const length = Math.max(0, endIndex - startIndex);
  const defect_id: number[] = [];
  const rough_bin: number[] = [];
  const class_number: number[] = [];
  const images: number[] = [];
  const test_id: number[] = [];
  const wafer_x: number[] = [];
  const wafer_y: number[] = [];
  const index_x: number[] = [];
  const index_y: number[] = [];
  const adder: number[] = [];
  const cluster_id: number[] = [];
  const die_x: number[] = [];
  const die_y: number[] = [];
  const reticle_x: number[] = [];
  const reticle_y: number[] = [];
  const size_x: number[] = [];
  const size_y: number[] = [];
  const size_d: number[] = [];
  const area: number[] = [];
  const final_bin: number[] = [];
  const manual_bin: number[] = [];
  const kill_ratio: number[] = [];

  for (let offset = 0; offset < length; offset += 1) {
    const index = startIndex + offset;
    defect_id.push(index + 1);
    rough_bin.push((index % 5) + 1);
    class_number.push((index % 10) + 1);
    images.push((index % 3) + 1);
    test_id.push(Math.floor(index / 100));
    wafer_x.push(-80_000_000 + ((index * 160) % 160_000_000));
    wafer_y.push(-80_000_000 + ((index * 131) % 160_000_000));
    index_x.push(index % 500);
    index_y.push(Math.floor(index / 500));
    adder.push(0);
    cluster_id.push(index % 20);
    die_x.push(index % 10);
    die_y.push(Math.floor(index / 10) % 10);
    reticle_x.push(index % 5);
    reticle_y.push(Math.floor(index / 5) % 5);
    size_x.push(50 + (index % 200));
    size_y.push(50 + (index % 200));
    size_d.push(70 + (index % 180));
    area.push(2000 + (index % 50_000));
    final_bin.push((index % 7) + 1);
    manual_bin.push((index % 3) + 1);
    kill_ratio.push((index % 100) / 100);
  }

  return {
    defect_id,
    rough_bin,
    class_number,
    images,
    test_id,
    wafer_x,
    wafer_y,
    index_x,
    index_y,
    adder,
    cluster_id,
    die_x,
    die_y,
    reticle_x,
    reticle_y,
    size_x,
    size_y,
    size_d,
    area,
    final_bin,
    manual_bin,
    kill_ratio,
  };
}

async function buildTable(total: number, seq: number): Promise<void> {
  if (!client) return;
  const nextTable = await client.table(
    {
      defect_id: "integer",
      rough_bin: "integer",
      class_number: "integer",
      images: "integer",
      test_id: "integer",
      wafer_x: "integer",
      wafer_y: "integer",
      index_x: "integer",
      index_y: "integer",
      adder: "integer",
      cluster_id: "integer",
      die_x: "integer",
      die_y: "integer",
      reticle_x: "integer",
      reticle_y: "integer",
      size_x: "integer",
      size_y: "integer",
      size_d: "integer",
      area: "integer",
      final_bin: "integer",
      manual_bin: "integer",
      kill_ratio: "float",
    },
    { index: "defect_id" },
  );

  for (let start = 0; start < total; start += CHUNK_SIZE) {
    if (seq !== rebuildSeq) {
      await nextTable.delete();
      return;
    }
    const end = Math.min(start + CHUNK_SIZE, total);
    await nextTable.update(rowChunk(start, end));
  }

  if (seq !== rebuildSeq) {
    await nextTable.delete();
    return;
  }

  const previousTable = table.value;
  table.value = nextTable;
  sourceVersion.value += 1;
  if (previousTable) {
    try {
      await previousTable.delete();
    } catch {
      /* best effort */
    }
  }
}

async function rebuildTable(): Promise<void> {
  if (!client) return;
  const seq = ++rebuildSeq;
  loading.value = true;
  const staleTable = table.value;
  table.value = null;
  if (staleTable) {
    try {
      await staleTable.delete();
    } catch {
      /* best effort */
    }
  }
  error.value = null;
  lastAction.value = `Rebuilding worker table with ${demoTotal.value.toLocaleString()} rows`;
  try {
    await buildTable(demoTotal.value, seq);
    if (seq === rebuildSeq) {
      lastAction.value = `Worker table ready: ${demoTotal.value.toLocaleString()} rows`;
    }
  } catch (caught) {
    if (seq === rebuildSeq) {
      error.value = caught instanceof Error ? caught.message : String(caught);
    }
  } finally {
    if (seq === rebuildSeq) loading.value = false;
  }
}

onMounted(async () => {
  try {
    await perspective.init_client(fetch(clientWasmUrl));
    perspective.init_server(fetch(serverWasmUrl));
    client = await perspective.worker();
    await rebuildTable();
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : String(caught);
    loading.value = false;
  }
});

onUnmounted(() => {
  rebuildSeq += 1;
  if (table.value) {
    try {
      table.value.delete();
    } catch {
      /* best effort */
    }
  }
  if (client) {
    try {
      client.terminate();
    } catch {
      /* best effort */
    }
  }
});

function handleSelectionChange(ids: number[]): void {
  lastAction.value = `Selection: ${ids.length} items`;
}
</script>

<style scoped>
.vxe-sandbox {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 12px;
  gap: 8px;
  box-sizing: border-box;
}

.vxe-sandbox-toolbar {
  flex-shrink: 0;
  padding: 8px 12px;
  background: var(--cv-card-bg, #1a1a2e);
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
}

.vxe-sandbox-table {
  flex: 1;
  min-height: 0;
  display: flex;
}

.vxe-sandbox-footer {
  flex-shrink: 0;
  padding: 4px 12px;
  font-size: 12px;
}
</style>
