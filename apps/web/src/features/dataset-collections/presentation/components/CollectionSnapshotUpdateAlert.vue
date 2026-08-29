<script setup lang="ts">
import { NAlert, NButton, NText } from "naive-ui";
import { useI18n } from "vue-i18n";

defineProps<{
  outdatedMemberCount: number;
  snapshotRevisionNumber: number | null;
  canModify: boolean;
  loading: boolean;
}>();

defineEmits<{
  refresh: [];
}>();
const { t } = useI18n();
</script>

<template>
  <NAlert
    :title="t('collectionDetail.updateAvailable')"
    type="warning"
    class="snapshot-update-alert"
  >
    <div class="snapshot-update-content">
      <div>
        <strong>
          {{
            t(
              "collectionDetail.outdatedMembers",
              { count: outdatedMemberCount },
              outdatedMemberCount,
            )
          }}
        </strong>
        {{ t("collectionDetail.refreshExplanation") }}
        <NText v-if="snapshotRevisionNumber !== null" depth="3">
          {{ t("collectionDetail.currentSnapshot", { revision: snapshotRevisionNumber }) }}
        </NText>
        <NText v-if="!canModify" depth="3">
          {{ t("collectionDetail.creatorRefreshOnly") }}
        </NText>
      </div>
      <NButton
        data-testid="refresh-collection-snapshot"
        type="primary"
        :disabled="!canModify"
        :loading="loading"
        @click="$emit('refresh')"
      >
        {{ t("collectionDetail.refreshSnapshot") }}
      </NButton>
    </div>
  </NAlert>
</template>

<style scoped>
.snapshot-update-content {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.snapshot-update-content > div {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

@media (max-width: 640px) {
  .snapshot-update-content {
    flex-direction: column;
  }

  .snapshot-update-content :deep(.n-button) {
    width: 100%;
  }
}
</style>
