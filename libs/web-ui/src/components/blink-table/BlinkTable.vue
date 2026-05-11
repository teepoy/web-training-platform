<!--
  BlinkTable — virtualized comparison table with A/B blink image toggle.

  Renders a scrollable list of rows, each with an optional blink image cell
  (BlinkImageCell) followed by data columns driven by the `columns` prop.
  Uses @tanstack/vue-virtual for efficient rendering of large datasets.

  The global blink toggle in the toolbar controls whether the first (image)
  column is rendered at all — when disabled it is structurally removed.
-->
<script setup lang="ts">
import { ref } from "vue";
import { useVirtualizer } from "@tanstack/vue-virtual";
import { NSwitch, NText } from "naive-ui";
import { useBlinkController } from "../../composables/useBlinkController";
import type { BlinkRow, BlinkColumnDef } from "../../types/blink-table";
import BlinkImageCell from "./BlinkImageCell.vue";

const props = withDefaults(
  defineProps<{
    rows: BlinkRow[];
    columns: BlinkColumnDef[];
    blinkIntervalMs?: number;
    initialBlinkEnabled?: boolean;
  }>(),
  {
    blinkIntervalMs: 1000,
    initialBlinkEnabled: true,
  },
);

const ROW_HEIGHT = 100;

const { enabled, phase, toggle } = useBlinkController({
  intervalMs: props.blinkIntervalMs,
  initialEnabled: props.initialBlinkEnabled,
});

const scrollRef = ref<HTMLElement | null>(null);

const virtualizer = useVirtualizer({
  get count() {
    return props.rows.length;
  },
  getScrollElement: () => scrollRef.value,
  estimateSize: () => ROW_HEIGHT,
  overscan: 3,
});

/** Resolve the optional width for a column, defaulting to flex-1 (or 120px for image). */
function colStyle(col: BlinkColumnDef): Record<string, string> {
  const w = col.width ?? (col.kind === "image" ? 120 : undefined);
  if (w) {
    return { flex: `0 0 ${w}px`, minWidth: "0" };
  }
  return { flex: "1", minWidth: "0" };
}
</script>

<template>
  <div class="bt">
    <!-- Toolbar -->
    <div class="bt-toolbar">
      <div class="bt-toolbar-left">
        <NSwitch :value="enabled" @update:value="toggle" />
        <NText depth="2" class="bt-blink-label">Blink</NText>
      </div>
      <div class="bt-toolbar-right">
        <NText depth="3" class="bt-row-count">
          {{ rows.length }} row{{ rows.length === 1 ? "" : "s" }}
        </NText>
      </div>
    </div>

    <!-- Column headers -->
    <div class="bt-header">
      <div
        v-if="enabled"
        class="bt-header-cell bt-header-cell--image"
      >
        <span class="bt-header-label">Blink</span>
      </div>
      <div
        v-for="col in columns"
        :key="col.key"
        class="bt-header-cell"
        :style="colStyle(col)"
      >
        <span class="bt-header-label">{{ col.title }}</span>
      </div>
    </div>

    <!-- Virtualized body -->
    <div ref="scrollRef" class="bt-scroll">
      <div
        :style="{
          height: virtualizer.getTotalSize() + 'px',
          position: 'relative',
          width: '100%',
        }"
      >
        <div
          v-for="vRow in virtualizer.getVirtualItems()"
          :key="vRow.index"
          :style="{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: vRow.size + 'px',
            transform: `translateY(${vRow.start}px)`,
          }"
        >
          <div class="bt-row">
            <BlinkImageCell
              v-if="enabled"
              :imageA="rows[vRow.index].imageA"
              :imageB="rows[vRow.index].imageB"
              :phase="phase"
            />
            <div class="bt-data">
              <div
                v-for="col in columns"
                :key="col.key"
                class="bt-cell"
                :style="colStyle(col)"
              >
                <img
                  v-if="col.kind === 'image'"
                  :src="rows[vRow.index].cells[col.key]"
                  class="bt-cell-img"
                  loading="lazy"
                  alt=""
                />
                <span v-else class="bt-cell-text">{{
                  rows[vRow.index].cells[col.key]
                }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="rows.length === 0" class="bt-empty">
        <NText depth="3">No rows to display</NText>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bt {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--cv-card-bg, #1e1e2e);
  border: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  border-radius: 8px;
  overflow: hidden;
}

/* ── Toolbar ─────────────────────────────────────────────── */

.bt-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  background: color-mix(
    in srgb,
    var(--cv-card-bg, #1e1e2e) 50%,
    var(--cv-bg, #16162a)
  );
  flex-shrink: 0;
}

.bt-toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.bt-toolbar-right {
  display: flex;
  align-items: center;
}

.bt-blink-label {
  font-size: 13px;
  font-weight: 500;
}

.bt-row-count {
  font-size: 12px;
}

/* ── Column headers ──────────────────────────────────────── */

.bt-header {
  display: flex;
  align-items: center;
  padding: 0 12px;
  height: 32px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.08));
  background: color-mix(
    in srgb,
    var(--cv-card-bg, #1e1e2e) 75%,
    var(--cv-bg, #16162a)
  );
  flex-shrink: 0;
  gap: 8px;
}

.bt-header-cell {
  display: flex;
  align-items: center;
  min-width: 0;
}

.bt-header-cell--image {
  flex: 0 0 120px;
  min-width: 0;
}

.bt-header-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--cv-text-secondary, rgba(255, 255, 255, 0.5));
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Scroll body ─────────────────────────────────────────── */

.bt-scroll {
  flex: 1;
  overflow-y: auto;
  position: relative;
}

.bt-scroll::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.bt-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.bt-scroll::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}

.bt-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}

/* ── Row ─────────────────────────────────────────────────── */

.bt-row {
  display: flex;
  align-items: center;
  padding: 5px 12px;
  gap: 8px;
  height: 100%;
  box-sizing: border-box;
}

.bt-row:nth-child(odd) {
  background: color-mix(
    in srgb,
    var(--cv-card-bg, #1e1e2e) 60%,
    var(--cv-bg, #16162a)
  );
}

/* ── Data columns─────────────────────────────────────────── */

.bt-data {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  gap: 8px;
}

.bt-cell {
  display: flex;
  align-items: center;
  min-width: 0;
}

.bt-cell-text {
  font-size: 13px;
  color: var(--cv-text, #fff);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  width: 100%;
}

.bt-cell-img {
  width: 100%;
  height: 90px;
  object-fit: cover;
  border-radius: 4px;
  background: #111;
  display: block;
}

/* ── Empty state ─────────────────────────────────────────── */

.bt-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 200px;
}
</style>
