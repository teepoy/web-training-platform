<script setup lang="ts">
import { ref, watchEffect } from "vue";
import { NButton, NInput, NSpace, NText } from "naive-ui";
import { parseDefectIds } from "./defectIdImport";

const props = defineProps<{
  appliedValues: Array<string | number>;
}>();

const emit = defineEmits<{
  (e: "apply", value: Array<string | number>): void;
  (e: "close"): void;
}>();

const text = ref("");
const fileInput = ref<HTMLInputElement | null>(null);
const importStatus = ref("");
const validationError = ref("");

watchEffect(() => {
  text.value = props.appliedValues.map(String).join(", ");
});

function apply(): void {
  const parsed = parseDefectIds(text.value);
  if (parsed.values.length === 0 && text.value.trim()) {
    validationError.value = "No valid integer Defect IDs found.";
    return;
  }
  validationError.value = "";
  emit("apply", parsed.values);
  emit("close");
}

function clear(): void {
  text.value = "";
  importStatus.value = "";
  validationError.value = "";
  emit("apply", []);
  emit("close");
}

function chooseFile(): void {
  fileInput.value?.click();
}

async function importFile(event: Event): Promise<void> {
  const input = event.currentTarget as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  try {
    const parsed = parseDefectIds(await file.text());
    if (parsed.values.length === 0) {
      importStatus.value = "";
      validationError.value = `${file.name} contains no valid integer Defect IDs.`;
      return;
    }
    text.value = parsed.values.join(", ");
    validationError.value = "";
    importStatus.value = `Loaded ${parsed.values.length.toLocaleString()} unique ID${
      parsed.values.length === 1 ? "" : "s"
    } from ${file.name}${
      parsed.invalidCount > 0 ? `; ignored ${parsed.invalidCount} invalid value(s)` : ""
    }.`;
  } catch {
    importStatus.value = "";
    validationError.value = `Could not read ${file.name}.`;
  }
}
</script>

<template>
  <div class="sst-filter-popover">
    <div class="sst-defect-filter-heading">
      <div>
        <NText strong class="sst-defect-filter-title">Defect IDs</NText>
        <NText depth="3" class="sst-defect-filter-hint">
          Paste a list or import a TXT/CSV file.
        </NText>
      </div>
      <input
        ref="fileInput"
        class="sst-file-input"
        type="file"
        accept=".txt,.csv,text/plain,text/csv"
        aria-label="Import defect IDs from file"
        @change="importFile"
      />
      <NButton size="tiny" secondary @click="chooseFile">Import file</NButton>
    </div>
    <NInput
      :value="text"
      type="textarea"
      placeholder="e.g. 1001, 1002, 1003"
      size="small"
      clearable
      :autosize="{ minRows: 2, maxRows: 5 }"
      @update:value="text = $event"
    />
    <NText v-if="importStatus" type="success" class="sst-defect-filter-status">
      {{ importStatus }}
    </NText>
    <NText v-if="validationError" type="error" class="sst-defect-filter-status">
      {{ validationError }}
    </NText>
    <NSpace :size="4">
      <NButton size="tiny" type="primary" @click="apply">Apply</NButton>
      <NButton size="tiny" quaternary @click="clear">Clear</NButton>
    </NSpace>
  </div>
</template>

<style scoped>
.sst-filter-popover {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  max-width: min(320px, calc(100vw - 48px));
  min-width: 0;
  width: 260px;
}

.sst-defect-filter-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.sst-defect-filter-title,
.sst-defect-filter-hint {
  display: block;
}

.sst-defect-filter-title {
  font-size: 12px;
}

.sst-defect-filter-hint,
.sst-defect-filter-status {
  font-size: 11px;
  line-height: 16px;
}

.sst-file-input {
  display: none;
}
</style>
