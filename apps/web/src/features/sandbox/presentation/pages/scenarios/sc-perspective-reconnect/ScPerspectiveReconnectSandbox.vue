<template>
  <div class="sc-reconnect-sandbox">
    <perspective-viewer class="sc-reconnect-hidden-viewer" aria-hidden="true" />
    <div class="sc-reconnect-toolbar">
      <NSpace align="center" :wrap="true">
        <NText strong>Real SC Perspective websocket</NText>
        <NInput v-model:value="inspectionTime" size="small" style="width: 290px" />
        <NInputNumber v-model:value="waferKey" :min="1" size="small" style="width: 90px" />
        <NDivider vertical />
        <NButton size="small" type="primary" @click="connect">Connect</NButton>
        <NButton size="small" @click="readTableSize">Read table size</NButton>
        <NButton size="small" @click="forceReconnect">Force reconnect</NButton>
        <NButton size="small" quaternary @click="disconnect">Disconnect</NButton>
      </NSpace>
    </div>

    <div class="sc-reconnect-state">
      <NSpace align="center" :wrap="true">
        <NTag :type="workbench.connected.value ? 'success' : 'default'">
          connected: {{ String(workbench.connected.value) }}
        </NTag>
        <NTag :type="workbench.dataReady.value ? 'success' : 'warning'">
          dataReady: {{ String(workbench.dataReady.value) }}
        </NTag>
        <NTag :type="workbench.table.value ? 'success' : 'default'">
          table: {{ workbench.table.value ? "open" : "none" }}
        </NTag>
        <NText v-if="workbench.error.value" depth="2">{{ workbench.error.value }}</NText>
      </NSpace>
    </div>

    <div class="sc-reconnect-log">
      <NList bordered>
        <NListItem v-for="entry in logEntries" :key="entry.id">
          <NText depth="3">{{ entry.time }}</NText>
          <NText>{{ entry.message }}</NText>
        </NListItem>
      </NList>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onUnmounted, ref, watch } from "vue";
import "@perspective-dev/viewer/inline";
import {
  NButton,
  NDivider,
  NInput,
  NInputNumber,
  NList,
  NListItem,
  NSpace,
  NTag,
  NText,
} from "naive-ui";
import { useScPerspectiveWorkbench } from "@/features/sc/presentation/composables/useScPerspectiveWorkbench";

interface LogEntry {
  id: number;
  time: string;
  message: string;
}

const inspectionTime = ref("2026-07-05T04:00:00+08:00");
const waferKey = ref(1);
const logEntries = ref<LogEntry[]>([]);
let nextLogId = 1;

const workbench = useScPerspectiveWorkbench({
  clientProbeIntervalMs: 1_000,
  clientProbeTimeoutMs: 1_500,
});

function appendLog(message: string): void {
  logEntries.value = [
    {
      id: nextLogId,
      time: new Date().toLocaleTimeString(),
      message,
    },
    ...logEntries.value,
  ].slice(0, 120);
  nextLogId += 1;
}

async function connect(): Promise<void> {
  logEntries.value = [];
  appendLog(`connect inspection=${inspectionTime.value}, wafer=${waferKey.value}`);
  await workbench.connect({
    kind: "preview",
    inspectionTime: inspectionTime.value,
    waferKey: waferKey.value,
  });
}

async function readTableSize(): Promise<void> {
  const table = workbench.table.value;
  if (!table) {
    appendLog("table is not open");
    return;
  }
  try {
    const size = await table.size();
    appendLog(`table.size() -> ${size}`);
  } catch (err) {
    appendLog(`table.size() failed: ${err instanceof Error ? err.message : String(err)}`);
    workbench.requestReconnect("sandbox table.size failed", err);
  }
}

function forceReconnect(): void {
  const scheduled = workbench.requestReconnect(
    "sandbox forced reconnect",
    new Error("WebSocket transport error (sandbox)"),
  );
  appendLog(`force reconnect scheduled=${String(scheduled)}`);
}

function disconnect(): void {
  workbench.disconnect();
  appendLog("manual disconnect");
}

watch(
  () => workbench.connected.value,
  (value) => appendLog(`connected -> ${String(value)}`),
);

watch(
  () => workbench.dataReady.value,
  (value) => appendLog(`dataReady -> ${String(value)}`),
);

watch(
  () => workbench.error.value,
  (value) => {
    if (value) appendLog(`error -> ${value}`);
  },
);

onUnmounted(() => {
  workbench.disconnect();
});
</script>

<style scoped>
.sc-reconnect-sandbox {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100vh;
  padding: 12px;
  box-sizing: border-box;
}

.sc-reconnect-hidden-viewer {
  position: absolute;
  width: 0;
  height: 0;
  overflow: hidden;
  opacity: 0;
  pointer-events: none;
}

.sc-reconnect-toolbar,
.sc-reconnect-state {
  flex: none;
  padding: 8px 12px;
  border: 1px solid var(--n-border-color);
  border-radius: 8px;
}

.sc-reconnect-log {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
</style>
