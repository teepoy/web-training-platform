<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { useMessage } from "naive-ui";
import { NForm, NFormItem, NInput, NDynamicTags, NButton, NSpace, NAlert } from "naive-ui";
import {
  createDatasetApiV1DatasetsPost,
  importSamplesApiV1DatasetsDatasetIdSamplesImportPost,
} from "@/generated/orval/endpoints/api";
import type { BulkCreateSampleItem } from "@/generated/orval/models";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import { useOrgStore } from "@/features/auth/application/org";
import type { ImporterProps } from "@/shared/widgets/sdk";

const props = defineProps<ImporterProps>();

const message = useMessage();
const { t } = useI18n();
const qc = useQueryClient();
const orgStore = useOrgStore();

const name = ref("");
const labelSpace = ref<string[]>([]);
const importItems = ref<BulkCreateSampleItem[]>([]);
const importFileName = ref("");

const importDataset = useMutation({
  mutationFn: async (payload: {
    name: string;
    label_space: string[];
    items: BulkCreateSampleItem[];
  }) => {
    const dataset = await createDatasetApiV1DatasetsPost({
      name: payload.name,
      dataset_type: "image_classification",
      task_spec: { task_type: "classification", label_space: payload.label_space },
    });
    const chunkSize = 5000;
    for (let offset = 0; offset < payload.items.length; offset += chunkSize) {
      const chunk = payload.items.slice(offset, offset + chunkSize);
      await importSamplesApiV1DatasetsDatasetIdSamplesImportPost(dataset.id!, { items: chunk });
    }
    return dataset;
  },
  onSuccess: () => {
    message.success(t("datasetFlows.datasetImported"));
    qc.invalidateQueries({
      queryKey: orgScopedQueryKey(orgStore.currentOrgId, ["api", "v1", "datasets"]),
    });
    props.onComplete({ imported: importItems.value.length, failed: 0 });
  },
  onError: (error) => {
    message.error(toUserMessage(error, t("datasetFlows.importFailed")));
  },
});

async function handleFileChange(event: Event) {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) {
    importItems.value = [];
    importFileName.value = "";
    return;
  }
  try {
    const text = await file.text();
    const parsed = JSON.parse(text);
    if (!Array.isArray(parsed)) {
      throw new Error(t("datasetFlows.jsonArrayRequired"));
    }
    importItems.value = parsed.map((item: Record<string, unknown>) => ({
      image_uris: Array.isArray(item?.image_uris) ? (item.image_uris as string[]) : [],
      metadata:
        typeof item?.metadata === "object" && item?.metadata !== null
          ? (item.metadata as Record<string, unknown>)
          : {},
      label: item?.label == null ? null : String(item.label),
    }));
    importFileName.value = `${file.name} (${importItems.value.length} samples)`;
  } catch (err: unknown) {
    importItems.value = [];
    importFileName.value = "";
    message.error((err as Error).message ?? t("datasetFlows.parseFailed"));
  }
}

function onSubmit() {
  if (!name.value) {
    message.error(t("datasetFlows.nameRequired"));
    return;
  }
  if (labelSpace.value.length === 0) {
    message.error(t("datasetFlows.labelsRequired"));
    return;
  }
  if (importItems.value.length === 0) {
    message.error(t("datasetFlows.jsonRequired"));
    return;
  }
  importDataset.mutate({
    name: name.value,
    label_space: labelSpace.value,
    items: importItems.value,
  });
}
</script>

<template>
  <NForm label-placement="left" label-width="110px">
    <NFormItem :label="t('common.name')">
      <NInput v-model:value="name" placeholder="e.g. imported-dataset" clearable />
    </NFormItem>

    <NFormItem :label="t('datasetFlows.taskType')">
      <NInput value="classification" disabled />
    </NFormItem>

    <NFormItem :label="t('datasetFlows.labelSpace')">
      <NDynamicTags v-model:value="labelSpace" />
    </NFormItem>

    <NFormItem :label="t('datasetFlows.samplesJson')">
      <input type="file" accept="application/json" @change="handleFileChange" />
    </NFormItem>

    <NAlert v-if="importFileName" type="info" :show-icon="false">
      {{ importFileName }}
    </NAlert>

    <NSpace justify="end" style="margin-top: 16px">
      <NButton @click="props.onCancel">{{ t("common.cancel") }}</NButton>
      <NButton type="primary" :loading="importDataset.isPending.value" @click="onSubmit">
        Import
      </NButton>
    </NSpace>
  </NForm>
</template>
