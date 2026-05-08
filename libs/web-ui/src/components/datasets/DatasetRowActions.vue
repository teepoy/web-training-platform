<script setup lang="ts">
import { NButton } from "naive-ui";

import type { DatasetListItem } from "../../datasets/types";

const props = defineProps<{
  row: DatasetListItem;
  isSuperadmin: boolean;
  isOwnOrg: boolean;
}>();

const emit = defineEmits<{
  view: [id: string];
  "toggle-public": [payload: { id: string; isPublic: boolean }];
  delete: [row: DatasetListItem];
}>();

function onView(e: MouseEvent): void {
  e.stopPropagation();
  emit("view", props.row.id);
}

function onTogglePublic(e: MouseEvent): void {
  e.stopPropagation();
  emit("toggle-public", { id: props.row.id, isPublic: !props.row.is_public });
}

function onDelete(e: MouseEvent): void {
  e.stopPropagation();
  emit("delete", props.row);
}
</script>

<template>
  <span>
    <NButton size="small" @click="onView">View</NButton>
    <template v-if="isSuperadmin && isOwnOrg">
      <NButton size="small" style="margin-left: 6px" @click="onTogglePublic">
        {{ row.is_public ? "Make Private" : "Make Public" }}
      </NButton>
      <NButton size="small" type="error" style="margin-left: 6px" @click="onDelete">
        Delete
      </NButton>
    </template>
  </span>
</template>
