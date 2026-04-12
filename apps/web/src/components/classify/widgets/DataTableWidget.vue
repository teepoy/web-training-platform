<!--
  DataTableWidget — sortable table rendered from inline column/row data.

  Inline data shape: { inline: { columns: string[], rows: any[][] } }

  Config props:
    maxRows — cap visible rows (default 100)
    striped — alternate row shading (default true)
-->
<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  data?: Record<string, unknown> | null
  config?: Record<string, unknown>
  size?: 'compact' | 'normal' | 'large'
}>()

const maxRows = computed(() => Number(props.config?.maxRows ?? 100))

interface TableData {
  columns: string[]
  rows: unknown[][]
}

const tableData = computed<TableData | null>(() => {
  if (!props.data) return null
  const raw = (props.data as Record<string, unknown>).inline ?? props.data
  if (!raw || typeof raw !== 'object') return null
  const d = raw as Record<string, unknown>
  const columns = d.columns
  const rows = d.rows
  if (!Array.isArray(columns) || !Array.isArray(rows)) return null
  return {
    columns: columns as string[],
    rows: (rows as unknown[][]).slice(0, maxRows.value),
  }
})

const sortCol = ref<number | null>(null)
const sortAsc = ref(true)

function toggleSort(colIdx: number) {
  if (sortCol.value === colIdx) {
    sortAsc.value = !sortAsc.value
  } else {
    sortCol.value = colIdx
    sortAsc.value = true
  }
}

const sortedRows = computed<unknown[][] | null>(() => {
  if (!tableData.value) return null
  const rows = [...tableData.value.rows]
  if (sortCol.value === null) return rows
  const ci = sortCol.value
  const dir = sortAsc.value ? 1 : -1
  rows.sort((a, b) => {
    const va = a[ci]
    const vb = b[ci]
    if (va === vb) return 0
    if (va == null) return 1
    if (vb == null) return -1
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir
    return String(va).localeCompare(String(vb)) * dir
  })
  return rows
})

const containerHeight = computed(() => {
  switch (props.size) {
    case 'compact': return '140px'
    case 'large': return '300px'
    default: return '200px'
  }
})
</script>

<template>
  <div class="dtw">
    <div v-if="!tableData" class="dtw-empty">No table data</div>
    <div v-else class="dtw-scroll" :style="{ maxHeight: containerHeight }">
      <table class="dtw-table">
        <thead>
          <tr>
            <th
              v-for="(col, i) in tableData.columns"
              :key="i"
              @click="toggleSort(i)"
              class="dtw-th"
            >
              {{ col }}
              <span v-if="sortCol === i" class="dtw-sort">{{ sortAsc ? '▲' : '▼' }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, ri) in sortedRows"
            :key="ri"
            :class="{ 'dtw-row--alt': ri % 2 === 1 }"
          >
            <td v-for="(cell, ci) in row" :key="ci" class="dtw-td">
              {{ cell ?? '' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="tableData" class="dtw-footer">
      {{ tableData.rows.length }} rows
    </div>
  </div>
</template>

<style scoped>
.dtw {
  width: 100%;
}
.dtw-empty {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  padding: 12px 0;
  text-align: center;
}
.dtw-scroll {
  overflow: auto;
}
.dtw-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.dtw-th {
  position: sticky;
  top: 0;
  background: rgba(30, 30, 46, 0.95);
  color: rgba(255, 255, 255, 0.7);
  font-weight: 600;
  padding: 4px 6px;
  text-align: left;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}
.dtw-th:hover {
  color: #fff;
}
.dtw-sort {
  margin-left: 2px;
  font-size: 9px;
}
.dtw-td {
  padding: 3px 6px;
  color: rgba(255, 255, 255, 0.75);
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 150px;
}
.dtw-row--alt {
  background: rgba(255, 255, 255, 0.02);
}
.dtw-footer {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.35);
  padding: 4px 0 0;
  text-align: right;
}
</style>
