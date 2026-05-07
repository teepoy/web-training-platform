<script setup lang="ts">
import { ref, computed, watch } from "vue"
import { NModal, NButton, NSpace, NIcon } from "naive-ui"
import PluginTypeSelector, { type PluginCard } from "./PluginTypeSelector.vue"

type PluginKind = "import" | "export" | "preview"

const props = defineProps<{
  show: boolean
  plugins: PluginCard[]
  kind: PluginKind
  title?: string
  datasetId?: string
}>()

const emit = defineEmits<{
  "update:show": [value: boolean]
  complete: [result: unknown]
}>()

const step = ref<"select" | "execute">("select")
const selectedPlugin = ref<PluginCard | null>(null)

watch(() => props.show, (v) => {
  if (v) {
    step.value = "select"
    selectedPlugin.value = null
  }
})

const modalTitle = computed(() => {
  if (step.value === "execute" && selectedPlugin.value) {
    return selectedPlugin.value.label
  }
  return props.title ?? (props.kind === "import" ? "Import" : props.kind === "export" ? "Export" : "Preview")
})

function handleSelect(plugin: PluginCard) {
  selectedPlugin.value = plugin
  step.value = "execute"
}

function handleComplete(result?: unknown) {
  emit("complete", result)
  emit("update:show", false)
}

function handleCancel() {
  if (step.value === "execute") {
    step.value = "select"
    selectedPlugin.value = null
  } else {
    emit("update:show", false)
  }
}

function handleBack() {
  step.value = "select"
  selectedPlugin.value = null
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    :title="modalTitle"
    style="max-width: 640px"
    :mask-closable="false"
    @update:show="emit('update:show', $event)"
  >
    <template v-if="step === 'select'">
      <PluginTypeSelector
        :plugins="plugins"
        @select="handleSelect"
      />
    </template>
    <template v-else-if="step === 'execute' && selectedPlugin">
      <component
        :is="selectedPlugin.component"
        v-if="kind === 'import'"
        :dataset-id="datasetId ?? ''"
        :on-complete="handleComplete"
        :on-cancel="handleCancel"
      />
      <component
        :is="selectedPlugin.component"
        v-else-if="kind === 'export'"
        :dataset-id="datasetId ?? ''"
        :on-complete="handleComplete"
        :on-cancel="handleCancel"
      />
      <component
        :is="selectedPlugin.component"
        v-else
        :on-complete="handleComplete"
        :on-cancel="handleCancel"
      />
    </template>
    <template #footer>
      <NSpace justify="space-between">
        <NButton v-if="step === 'execute'" @click="handleBack">
          &larr; Back
        </NButton>
        <span v-else />
        <NButton @click="emit('update:show', false)">
          Cancel
        </NButton>
      </NSpace>
    </template>
  </NModal>
</template>