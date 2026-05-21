<script setup lang="ts">
import {
  NButton, NSpace, NSpin, NAlert, NRadioGroup, NRadioButton,
} from "naive-ui";
import {
  SampleBrowser,
  BrowserSidebar,
  COLLAPSED_SIDEBAR_WIDTH,
  MAX_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
} from "@/shared";
import { injectPreviewPage } from "../composables/usePreviewPage";
import { widgetRegistry } from "@/app/registrations";

const page = injectPreviewPage();
</script>

<template>
  <!-- Loading / Error states -->
  <div v-if="page.sessionLoading.value" class="preview-center">
    <NSpin size="large" />
  </div>
  <div v-else-if="page.sessionError.value" class="preview-center">
    <NAlert type="error" :title="page.sessionError.value" />
  </div>

  <!-- Main workspace -->
  <template v-else>
    <!-- Toolbar -->
    <div class="preview-toolbar">
      <NRadioGroup v-model:value="page.prefs.layout" size="small">
        <NRadioButton value="grid">Grid</NRadioButton>
        <NRadioButton value="list">List</NRadioButton>
      </NRadioGroup>
    </div>

    <!-- Notice about classification disabled -->
    <div v-if="!page.session.value?.classification_enabled" class="preview-notice-bar">
      <NAlert type="info" :show-icon="false" style="margin: 8px 16px;">
        Classification disabled until dataset is persisted.
      </NAlert>
    </div>

    <div class="preview-layout">
      <!-- Image grid -->
      <SampleBrowser
        :items="page.browserItems.value"
        :total-count="page.loader.estimatedTotal.value ?? page.loader.loadedCount.value"
        :thumb-size="page.prefs.thumbSize"
        :layout="page.prefs.layout"
        :is-loading="page.loader.isLoading.value"
        :selection-enabled="false"
        :show-checkboxes="false"
        :show-label-rail="false"
        :show-bottom-bar="false"
        activation-mode="open"
        @open-item="(id: string) => page.selectItem(
          page.loader.items.value.find(i => i.upstream_item_id === id)!
        )"
        @load-more="page.loader.loadMore()"
      />

      <!-- Sidebar area -->
      <div class="preview-sidebar-container" :class="{ collapsed: page.prefs.sidebarCollapsed }">
        <div class="preview-sidebar-actions">
          <NButton type="primary" block @click="page.showPersistModal.value = true">
            Persist Dataset
          </NButton>
        </div>
        <div style="flex: 1; min-height: 0; display: flex;">
          <BrowserSidebar
            :panels="page.previewSidebarPanels.value"
            :context="{}"
            :collapsed="page.prefs.sidebarCollapsed"
            :sidebar-width="page.prefs.sidebarWidth"
            :min-sidebar-width="MIN_SIDEBAR_WIDTH"
            :max-sidebar-width="MAX_SIDEBAR_WIDTH"
            :collapsed-sidebar-width="COLLAPSED_SIDEBAR_WIDTH"
            :component-resolver="(key: string) => widgetRegistry.getWidgetComponent(key) ?? null"
            @update:collapsed="page.prefs.setSidebarCollapsed"
            @update:sidebar-width="page.prefs.setSidebarWidth"
            style="border-left: none;"
          />
        </div>
      </div>
    </div>
  </template>
</template>

<style scoped>
.preview-toolbar {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  flex-shrink: 0;
}

.preview-center {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 300px;
}

.preview-notice-bar {
  flex-shrink: 0;
}

.preview-layout {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.preview-sidebar-container {
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  background: var(--cv-card-bg, #1e1e2e);
  transition: width 0.2s, min-width 0.2s;
}

.preview-sidebar-actions {
  padding: 12px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.08));
}

.preview-sidebar-container.collapsed .preview-sidebar-actions {
  display: none;
}
</style>
