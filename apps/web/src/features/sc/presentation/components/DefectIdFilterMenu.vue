<script setup lang="ts">
import { ref, watchEffect } from "vue";
import { NButton, NInput, NRadioButton, NRadioGroup, NText } from "naive-ui";
import { useI18n } from "vue-i18n";
import { parseDefectIds } from "./defectIdImport";
import TableFilterPopover from "@/shared/components/table-filter/TableFilterPopover.vue";
import { formatNumber } from "@/shared/i18n/format";

const props = defineProps<{
  appliedValues: Array<string | number>;
  exclude?: boolean;
}>();
const { t } = useI18n();

const emit = defineEmits<{
  (e: "apply", value: Array<string | number>, exclude: boolean): void;
  (e: "close"): void;
}>();

const text = ref("");
const fileInput = ref<HTMLInputElement | null>(null);
const importStatus = ref("");
const validationError = ref("");
const mode = ref<"include" | "exclude">("include");

watchEffect(() => {
  text.value = props.appliedValues.map(String).join(", ");
  mode.value = props.exclude ? "exclude" : "include";
});

function apply(): void {
  const parsed = parseDefectIds(text.value);
  if (parsed.values.length === 0 && text.value.trim()) {
    validationError.value = t("tableFilters.noValidIds");
    return;
  }
  validationError.value = "";
  emit("apply", parsed.values, mode.value === "exclude");
  emit("close");
}

function clear(): void {
  text.value = "";
  importStatus.value = "";
  validationError.value = "";
  mode.value = "include";
}

function cancel(): void {
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
      validationError.value = t("tableFilters.fileNoValidIds", { file: file.name });
      return;
    }
    text.value = parsed.values.join(", ");
    validationError.value = "";
    importStatus.value = t(
      "tableFilters.fileLoaded",
      {
        count: parsed.values.length,
        formattedCount: formatNumber(parsed.values.length),
        file: file.name,
      },
      parsed.values.length,
    );
    if (parsed.invalidCount > 0) {
      importStatus.value += ` ${t(
        "tableFilters.ignoredInvalid",
        { count: parsed.invalidCount, formattedCount: formatNumber(parsed.invalidCount) },
        parsed.invalidCount,
      )}`;
    }
  } catch {
    importStatus.value = "";
    validationError.value = t("tableFilters.fileReadFailed", { file: file.name });
  }
}
</script>

<template>
  <TableFilterPopover variant="text" @clear="clear" @cancel="cancel" @apply="apply">
    <div class="sst-defect-filter-heading">
      <div>
        <NText strong class="sst-defect-filter-title">{{ t("tableFilters.defectIds") }}</NText>
        <NText depth="3" class="sst-defect-filter-hint">
          {{ t("tableFilters.defectHint") }}
        </NText>
      </div>
      <input
        ref="fileInput"
        class="sst-file-input"
        type="file"
        accept=".txt,.csv,text/plain,text/csv"
        :aria-label="t('tableFilters.importDefectIds')"
        @change="importFile"
      />
      <NButton size="tiny" secondary @click="chooseFile">
        {{ t("tableFilters.importFile") }}
      </NButton>
    </div>
    <NInput
      :value="text"
      type="textarea"
      :placeholder="t('tableFilters.defectExample')"
      size="small"
      clearable
      :autosize="{ minRows: 2, maxRows: 5 }"
      @update:value="text = $event"
    />
    <NRadioGroup v-model:value="mode" size="small">
      <NRadioButton value="include">{{ t("tableFilters.includeOnly") }}</NRadioButton>
      <NRadioButton value="exclude">{{ t("tableFilters.exclude") }}</NRadioButton>
    </NRadioGroup>
    <NText v-if="importStatus" type="success" class="sst-defect-filter-status">
      {{ importStatus }}
    </NText>
    <NText v-if="validationError" type="error" class="sst-defect-filter-status">
      {{ validationError }}
    </NText>
  </TableFilterPopover>
</template>

<style scoped>
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
