<script setup lang="ts">
import { computed } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { NButton, NResult, NSpin } from "naive-ui";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import { getRevisionApiV1DatasetCollectionsCollectionIdRevisionsRevisionIdGet } from "@/generated/orval/endpoints/api";
import ReclassifyPage from "@/features/sc/presentation/pages/ReclassifyPage.vue";
import { getScClassifyLimits } from "@/features/sc/api/classifyLimits";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import { formatNumber } from "@/shared/i18n/format";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const orgStore = useOrgStore();
const collectionId = computed(() => String(route.params.collectionId));
const revisionId = computed(() => String(route.query.revisionId ?? ""));
const datasetKey = computed(
  () => `${collectionId.value}:${revisionId.value}:${String(route.params.id)}`,
);
const revisionQuery = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, [
      "dataset-collections",
      collectionId.value,
      "revisions",
      revisionId.value,
    ]),
  ),
  queryFn: () =>
    getRevisionApiV1DatasetCollectionsCollectionIdRevisionsRevisionIdGet(
      collectionId.value,
      revisionId.value,
    ),
  enabled: computed(() => !!orgStore.currentOrgId && !!collectionId.value && !!revisionId.value),
});
const limitsQuery = useQuery({
  queryKey: ["sc", "classify-limits"],
  queryFn: getScClassifyLimits,
});
const isLoading = computed(() => revisionQuery.isLoading.value || limitsQuery.isLoading.value);
const loadError = computed(() => revisionQuery.error.value ?? limitsQuery.error.value ?? null);
const exceedsLimit = computed(() => {
  const rows = revisionQuery.data.value?.row_count;
  const maximum = limitsQuery.data.value?.max_rows;
  return rows !== null && rows !== undefined && maximum !== undefined && rows > maximum;
});
</script>

<template>
  <div v-if="isLoading" class="classify-gate"><NSpin size="large" /></div>
  <NResult
    v-else-if="!revisionId || loadError"
    status="error"
    :title="t('collectionDetail.classifyUnavailable')"
    :description="toUserMessage(loadError, t('collectionDetail.classifyRevisionRequired'))"
  >
    <template #footer>
      <NButton @click="router.push(`/dataset-collections/${collectionId}`)">
        {{ t("collectionDetail.backToCollection") }}
      </NButton>
    </template>
  </NResult>
  <NResult
    v-else-if="exceedsLimit"
    status="warning"
    :title="t('collectionDetail.classifyTooLargeTitle')"
    :description="
      t('collectionDetail.classifyTooLarge', {
        rows: formatNumber(revisionQuery.data.value?.row_count ?? 0),
        maximum: formatNumber(limitsQuery.data.value?.max_rows ?? 0),
      })
    "
  >
    <template #footer>
      <NButton @click="router.push(`/dataset-collections/${collectionId}`)">
        {{ t("collectionDetail.backToCollection") }}
      </NButton>
    </template>
  </NResult>
  <ReclassifyPage v-else :key="datasetKey" />
</template>

<style scoped>
.classify-gate {
  display: grid;
  min-height: 50vh;
  place-items: center;
}
</style>
