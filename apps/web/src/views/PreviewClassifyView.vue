<script setup lang="ts">
import {
  NModal, NSpace, NRadioGroup, NRadio, NButton,
} from "naive-ui";
import { PreviewItemDrawer } from "@/shared";
import { usePreviewPage } from "../features/preview/composables/usePreviewPage";
import PreviewBrowserArea from "../features/preview/components/PreviewBrowserArea.vue";

const page = usePreviewPage();
</script>

<template>
  <div class="preview-workspace">
    <PreviewBrowserArea />

    <PreviewItemDrawer
      :show="page.showDrawer.value"
      :item="page.selectedItem.value"
      @update:show="page.showDrawer.value = $event"
    />

    <NModal
      v-model:show="page.showPersistModal.value"
      preset="card"
      title="Persist Dataset"
      style="max-width: 420px;"
    >
      <NSpace vertical size="large">
        <p style="margin: 0; color: var(--n-text-color-2);">
          Choose what to persist as a new dataset:
        </p>
        <NRadioGroup v-model:value="page.persistScope.value">
          <NSpace vertical>
            <NRadio value="entire_collection">Entire collection (recommended)</NRadio>
            <NRadio value="loaded_items_only">Currently loaded items only</NRadio>
          </NSpace>
        </NRadioGroup>
        <NSpace justify="end">
          <NButton
            @click="page.showPersistModal.value = false"
            :disabled="page.isPersisting.value"
          >
            Cancel
          </NButton>
          <NButton
            type="primary"
            :loading="page.isPersisting.value"
            @click="page.handlePersist()"
          >
            Persist
          </NButton>
        </NSpace>
      </NSpace>
    </NModal>
  </div>
</template>

<style scoped>
.preview-workspace {
  height: 100%;
  display: flex;
  flex-direction: column;
}
</style>
