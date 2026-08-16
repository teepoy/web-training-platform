<script setup lang="ts">
import { NAlert, NButton, NText } from "naive-ui";

defineProps<{
  outdatedMemberCount: number;
  snapshotRevisionNumber: number | null;
  canModify: boolean;
  loading: boolean;
}>();

defineEmits<{
  refresh: [];
}>();
</script>

<template>
  <NAlert title="Update available" type="warning" class="snapshot-update-alert">
    <div class="snapshot-update-content">
      <div>
        <strong>
          {{ outdatedMemberCount }} linked Dataset{{
            outdatedMemberCount === 1 ? " has" : "s have"
          }}
          newer change numbers.
        </strong>
        Refreshing records the latest observed change number for every member in a new Collection
        Snapshot. It does not copy or freeze Dataset data, and it does not start prediction or
        training.
        <NText v-if="snapshotRevisionNumber !== null" depth="3">
          Current Snapshot: #{{ snapshotRevisionNumber }}.
        </NText>
        <NText v-if="!canModify" depth="3">
          Only the Collection creator can refresh this snapshot.
        </NText>
      </div>
      <NButton
        data-testid="refresh-collection-snapshot"
        type="primary"
        :disabled="!canModify"
        :loading="loading"
        @click="$emit('refresh')"
      >
        Refresh snapshot
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
