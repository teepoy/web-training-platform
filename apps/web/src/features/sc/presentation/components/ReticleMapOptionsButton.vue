<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { NButton, NIcon, NInputNumber, NModal, NSwitch } from "naive-ui";
import { SettingsOutline } from "@vicons/ionicons5";
import {
  normalizeReticleMapOptions,
  reticleMapOptionsEqual,
  type ReticleMapOptions,
} from "@/features/sc/application/reticleMapOptions";

const props = defineProps<{
  modelValue: ReticleMapOptions;
  size?: "tiny" | "small" | "medium" | "large";
  iconOnly?: boolean;
  quaternary?: boolean;
  showImageMarkers?: boolean;
  defectSize?: number;
}>();

const emit = defineEmits<{
  (e: "submit", value: ReticleMapOptions): void;
  (e: "submit-display", value: { showImageMarkers: boolean; defectSize: number }): void;
}>();

const showModal = ref(false);
const draft = ref<ReticleMapOptions>({ ...props.modelValue });
const draftShowImageMarkers = ref(props.showImageMarkers ?? true);
const draftDefectSize = ref(props.defectSize ?? 2);
const { t } = useI18n();

function openModal(): void {
  draft.value = { ...props.modelValue };
  draftShowImageMarkers.value = props.showImageMarkers ?? true;
  draftDefectSize.value = props.defectSize ?? 2;
  showModal.value = true;
}

function updateDraft(key: keyof ReticleMapOptions, value: number | null): void {
  draft.value = {
    ...draft.value,
    [key]: value ?? draft.value[key],
  };
}

function applyOptions(): void {
  const nextReticleOptions = normalizeReticleMapOptions(draft.value);
  const currentReticleOptions = normalizeReticleMapOptions(props.modelValue);
  if (!reticleMapOptionsEqual(nextReticleOptions, currentReticleOptions)) {
    emit("submit", nextReticleOptions);
  }

  const nextDisplayOptions = {
    showImageMarkers: draftShowImageMarkers.value,
    defectSize: draftDefectSize.value,
  };
  if (
    nextDisplayOptions.showImageMarkers !== (props.showImageMarkers ?? true) ||
    nextDisplayOptions.defectSize !== (props.defectSize ?? 2)
  ) {
    emit("submit-display", nextDisplayOptions);
  }
  showModal.value = false;
}
</script>

<template>
  <NButton
    data-testid="sc-map-settings"
    :size="size ?? 'tiny'"
    :quaternary="quaternary"
    :title="t('sc.mapSettings')"
    @click="openModal"
  >
    <template v-if="iconOnly" #icon>
      <NIcon><SettingsOutline /></NIcon>
    </template>
    <template v-if="!iconOnly">{{ t("sc.options") }}</template>
  </NButton>
  <NModal
    v-model:show="showModal"
    preset="card"
    :title="t('sc.mapSettings')"
    class="srmo-modal"
    :style="{ width: '520px', maxWidth: 'calc(100vw - 32px)' }"
  >
    <div class="srmo-grid">
      <h3>{{ t("sc.reticleLayout") }}</h3>
      <label>
        {{ t("sc.xDieCount") }}
        <NInputNumber
          :min="1"
          :precision="0"
          :value="draft.xDieCount"
          @update:value="(v) => updateDraft('xDieCount', v)"
        />
      </label>
      <label>
        {{ t("sc.yDieCount") }}
        <NInputNumber
          :min="1"
          :precision="0"
          :value="draft.yDieCount"
          @update:value="(v) => updateDraft('yDieCount', v)"
        />
      </label>
      <label>
        {{ t("sc.xDieShift") }}
        <NInputNumber
          :precision="0"
          :value="draft.xDieShift"
          @update:value="(v) => updateDraft('xDieShift', v)"
        />
      </label>
      <label>
        {{ t("sc.yDieShift") }}
        <NInputNumber
          :precision="0"
          :value="draft.yDieShift"
          @update:value="(v) => updateDraft('yDieShift', v)"
        />
      </label>
      <h3>{{ t("sc.defectDisplay") }}</h3>
      <label>
        {{ t("sc.imageBoxIndicator") }}
        <NSwitch v-model:value="draftShowImageMarkers" />
      </label>
      <label>
        {{ t("sc.defectSize") }}
        <NInputNumber v-model:value="draftDefectSize" :min="1" :max="24" :step="1" />
      </label>
    </div>
    <template #footer>
      <div class="srmo-footer">
        <NButton @click="showModal = false">{{ t("common.cancel") }}</NButton>
        <NButton type="primary" @click="applyOptions">{{ t("common.apply") }}</NButton>
      </div>
    </template>
  </NModal>
</template>

<style scoped>
.srmo-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.srmo-grid label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
}

.srmo-grid h3 {
  grid-column: 1 / -1;
  margin: 4px 0 0;
  font-size: 13px;
}

.srmo-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
