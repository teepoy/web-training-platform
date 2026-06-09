<script setup lang="ts">
import { ref, watch } from "vue"
import { useMutation, useQueryClient } from "@tanstack/vue-query"
import { useMessage } from "naive-ui"
import { NForm, NFormItem, NInput, NSelect, NDynamicTags, NButton, NSpace, NAlert } from "naive-ui"
import { createDataset } from "@/shared/api/datasets"
import { importSamples } from "@/shared/api/samples"
import type { BulkCreateSampleItem } from "@/generated/orval/models"
import type { ImporterProps } from "@/shared/widgets/sdk"

const props = defineProps<ImporterProps>()

const message = useMessage()
const qc = useQueryClient()

const name = ref("")
const datasetType = ref<string | null>(null)
const taskType = ref<string | null>(null)
const labelSpace = ref<string[]>([])
const importItems = ref<BulkCreateSampleItem[]>([])
const importFileName = ref("")

const datasetTypeOptions = [
  { label: "Image Classification", value: "image_classification" },
  { label: "Image Detection", value: "image_detection" },
  { label: "Image VQA", value: "image_vqa" },
]

watch(datasetType, (v) => {
  if (v === "image_classification") {
    taskType.value = "classification"
  } else if (v === "image_detection") {
    taskType.value = "detection"
  } else if (v === "image_vqa") {
    taskType.value = "vqa"
    labelSpace.value = []
  } else {
    taskType.value = null
  }
})

const importDataset = useMutation({
  mutationFn: async (payload: {
    name: string
    dataset_type: "image_classification" | "image_detection" | "image_vqa"
    task_type: "classification" | "detection" | "vqa"
    label_space: string[]
    items: BulkCreateSampleItem[]
  }) => {
    const dataset = await createDataset({
      name: payload.name,
      dataset_type: payload.dataset_type,
      task_spec: { task_type: payload.task_type, label_space: payload.label_space },
    })
    const chunkSize = 5000
    for (let offset = 0; offset < payload.items.length; offset += chunkSize) {
      const chunk = payload.items.slice(offset, offset + chunkSize)
      await importSamples(dataset.id!, chunk)
    }
    return dataset
  },
  onSuccess: () => {
    message.success("Dataset imported")
    qc.invalidateQueries({ queryKey: ["datasets"] })
    props.onComplete({ imported: importItems.value.length, failed: 0 })
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to import dataset")
  },
})

async function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) {
    importItems.value = []
    importFileName.value = ""
    return
  }
  try {
    const text = await file.text()
    const parsed = JSON.parse(text)
    if (!Array.isArray(parsed)) {
      throw new Error("Import file must be a JSON array of sample items")
    }
    importItems.value = parsed.map((item: Record<string, unknown>) => ({
      image_uris: Array.isArray(item?.image_uris) ? (item.image_uris as string[]) : [],
      metadata: typeof item?.metadata === "object" && item?.metadata !== null ? item.metadata as Record<string, unknown> : {},
      label: item?.label == null ? null : String(item.label),
    }))
    importFileName.value = `${file.name} (${importItems.value.length} samples)`
  } catch (err: unknown) {
    importItems.value = []
    importFileName.value = ""
    message.error((err as Error).message ?? "Failed to parse import file")
  }
}

function onSubmit() {
  if (!name.value || !datasetType.value || !taskType.value) {
    message.error("Dataset name and type are required")
    return
  }
  if (datasetType.value === "image_classification" && labelSpace.value.length === 0) {
    message.error("Label space is required for image classification datasets")
    return
  }
  if (importItems.value.length === 0) {
    message.error("Select a JSON file with samples to import")
    return
  }
  importDataset.mutate({
    name: name.value,
    dataset_type: datasetType.value! as "image_classification" | "image_detection" | "image_vqa",
    task_type: taskType.value! as "classification" | "detection" | "vqa",
    label_space: labelSpace.value,
    items: importItems.value,
  })
}
</script>

<template>
  <NForm label-placement="left" label-width="110px">
    <NFormItem label="Name">
      <NInput v-model:value="name" placeholder="e.g. imported-dataset" clearable />
    </NFormItem>

    <NFormItem label="Dataset Type">
      <NSelect
        v-model:value="datasetType"
        :options="datasetTypeOptions"
        placeholder="Select dataset type"
      />
    </NFormItem>

    <NFormItem label="Task Type">
      <NInput :value="taskType ?? ''" disabled />
    </NFormItem>

    <NFormItem v-if="datasetType === 'image_classification'" label="Label Space">
      <NDynamicTags v-model:value="labelSpace" />
    </NFormItem>

    <NFormItem label="Samples JSON">
      <input type="file" accept="application/json" @change="handleFileChange" />
    </NFormItem>

    <NAlert v-if="importFileName" type="info" :show-icon="false">
      {{ importFileName }}
    </NAlert>

    <NSpace justify="end" style="margin-top: 16px">
      <NButton @click="props.onCancel">Cancel</NButton>
      <NButton
        type="primary"
        :loading="importDataset.isPending.value"
        @click="onSubmit"
      >
        Import
      </NButton>
    </NSpace>
  </NForm>
</template>
