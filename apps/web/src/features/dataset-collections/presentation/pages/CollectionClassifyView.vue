<script setup lang="ts">
import { computed } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { NButton, NResult, NSpin } from "naive-ui";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import { getRevisionApiV1DatasetCollectionsCollectionIdRevisionsRevisionIdGet } from "@/generated/orval/endpoints/api";
import ReclassifyPage from "@/features/sc/presentation/pages/ReclassifyPage.vue";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const orgStore = useOrgStore();
const collectionId = computed(() => String(route.params.collectionId));
const revisionId = computed(() => String(route.params.revisionId ?? ""));
const workspaceKey = computed(() => `${collectionId.value}:${revisionId.value}`);
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
const isLoading = computed(() => revisionQuery.isLoading.value);
const loadError = computed(() => revisionQuery.error.value ?? null);
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
  <ReclassifyPage v-else :key="workspaceKey" />
</template>

<style scoped>
.classify-gate {
  display: grid;
  min-height: 50vh;
  place-items: center;
}
</style>
