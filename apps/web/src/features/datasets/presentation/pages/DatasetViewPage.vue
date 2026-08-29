<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useQuery } from "@tanstack/vue-query";
import { NButton, NResult, NSpin, NText } from "naive-ui";
import { getViewSamples } from "@/shared/api/datasets";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey } from "@/shared/api";
import {
  getViewSchema,
  listRegisteredViewTypes,
  resolveViewComponent,
} from "@/features/datasets/presentation/pages/schema-registry";

const props = defineProps<{
  datasetId: string;
  viewType: string;
}>();
const emit = defineEmits<{
  (event: "select-sample", sampleId: string): void;
}>();

const id = computed(() => props.datasetId);
const viewType = computed(() => props.viewType);
const orgStore = useOrgStore();
const { t } = useI18n();

const viewSchema = computed(() => getViewSchema(viewType.value));
const viewComponent = computed(() => resolveViewComponent(viewType.value));

const isViewValid = computed(() => {
  if (!viewSchema.value || !viewComponent.value) return false;
  return true;
});

const offset = ref(0);
const limit = 50;

const isSelfLoadingView = computed(() => viewSchema.value?.selfLoading === true);

const viewSamplesQuery = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, [
      "view-samples",
      id.value,
      viewType.value,
      offset.value,
      limit,
    ]),
  ),
  queryFn: () => getViewSamples(id.value, viewType.value, offset.value, limit),
  enabled: computed(
    () => !!orgStore.currentOrgId && isViewValid.value === true && !isSelfLoadingView.value,
  ),
  retry: false,
});

const viewData = computed(() => viewSamplesQuery.data.value);

function handleNextPage() {
  if (viewData.value && offset.value + limit < viewData.value.total) {
    offset.value += limit;
  }
}

function handlePrevPage() {
  if (offset.value >= limit) {
    offset.value -= limit;
  }
}
</script>

<template>
  <div>
    <n-result
      v-if="isViewValid === false"
      status="404"
      :title="t('datasetDetail.invalidView')"
      :description="
        t('datasetDetail.invalidViewHelp', {
          viewType,
          registered: listRegisteredViewTypes().join(', ') || t('datasetDetail.none'),
        })
      "
    />

    <template v-else>
      <n-spin
        v-if="!isSelfLoadingView && viewSamplesQuery.isLoading.value"
        style="display: flex; justify-content: center; padding: 48px"
      />

      <n-result
        v-else-if="!isSelfLoadingView && viewSamplesQuery.isError.value"
        status="error"
        :title="t('datasetDetail.viewLoadFailed')"
        :description="t('datasetDetail.viewLoadFailedHelp')"
      />

      <template v-else>
        <component
          :is="viewComponent"
          :dataset-id="id"
          :view-type="viewType"
          :items="viewData?.items ?? []"
          :total="viewData?.total ?? 0"
          @select-sample="emit('select-sample', $event)"
        />

        <div
          v-if="!isSelfLoadingView && viewData && viewData.total > limit"
          style="display: flex; justify-content: center; gap: 12px; margin-top: 16px"
        >
          <n-button :disabled="offset === 0" @click="handlePrevPage">
            {{ t("common.previous") }}
          </n-button>
          <n-text depth="3" style="line-height: 34px">
            {{
              t("common.pageRange", {
                start: offset + 1,
                end: Math.min(offset + limit, viewData.total),
                total: viewData.total,
              })
            }}
          </n-text>
          <n-button :disabled="offset + limit >= viewData.total" @click="handleNextPage">{{
            t("common.next")
          }}</n-button>
        </div>
      </template>
    </template>
  </div>
</template>
