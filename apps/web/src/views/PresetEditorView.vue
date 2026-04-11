<template>
  <div>
    <template v-if="!orgStore.currentOrgId">
      <div style="padding: 48px; text-align: center;">
        <n-empty description="You are not a member of any organization. Contact an admin." />
      </div>
    </template>
    <template v-else>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px">
      <n-h2 style="margin: 0">Training Presets</n-h2>
      <n-tag type="info" size="small">Read-only catalog</n-tag>
    </n-space>

    <n-spin :show="isLoading">
      <n-alert v-if="isError" type="error" style="margin-bottom: 12px">
        Failed to load presets: {{ (error as Error)?.message ?? 'Unknown error' }}
      </n-alert>
      <n-data-table
        :columns="columns"
        :data="presets ?? []"
        :bordered="false"
        :row-props="rowProps"
      />
    </n-spin>

    <!-- Preset Detail Drawer -->
    <n-drawer
      v-model:show="showDrawer"
      :width="560"
      placement="right"
    >
      <n-drawer-content :title="selectedPreset?.name ?? 'Preset'" closable>
        <template v-if="selectedPreset">
          <n-descriptions bordered :column="1" label-placement="left" size="small" style="margin-bottom: 16px">
            <n-descriptions-item label="ID">
              <n-text code>{{ selectedPreset.id }}</n-text>
            </n-descriptions-item>
            <n-descriptions-item label="Version">
              {{ selectedPreset.version ?? '-' }}
            </n-descriptions-item>
            <n-descriptions-item label="Description">
              {{ selectedPreset.description || '-' }}
            </n-descriptions-item>
            <n-descriptions-item label="Deprecated">
              <n-tag v-if="selectedPreset.deprecated" type="warning" size="small">Yes</n-tag>
              <span v-else>No</span>
            </n-descriptions-item>
          </n-descriptions>

          <n-h3>Model</n-h3>
          <n-descriptions bordered :column="1" label-placement="left" size="small" style="margin-bottom: 16px">
            <n-descriptions-item label="Framework">
              <n-tag type="info" size="small">{{ selectedPreset.model.framework }}</n-tag>
            </n-descriptions-item>
            <n-descriptions-item label="Base Model">
              {{ selectedPreset.model.base_model }}
            </n-descriptions-item>
            <n-descriptions-item v-if="selectedPreset.model.source" label="Source">
              {{ selectedPreset.model.source }}
            </n-descriptions-item>
          </n-descriptions>

          <n-h3>Training</n-h3>
          <n-descriptions bordered :column="1" label-placement="left" size="small" style="margin-bottom: 16px">
            <n-descriptions-item label="Process">
              <n-text code>{{ selectedPreset.train.process }}</n-text>
            </n-descriptions-item>
            <n-descriptions-item v-if="selectedPreset.train.dataloader" label="Dataloader">
              <n-text code>{{ selectedPreset.train.dataloader.ref }}</n-text>
            </n-descriptions-item>
            <n-descriptions-item v-if="selectedPreset.train.hyperparams" label="Hyperparams">
              <n-text code>{{ JSON.stringify(selectedPreset.train.hyperparams, null, 2) }}</n-text>
            </n-descriptions-item>
          </n-descriptions>

          <n-h3>Prediction Targets</n-h3>
          <n-descriptions
            v-for="(target, key) in selectedPreset.predict.targets"
            :key="key"
            bordered
            :column="1"
            label-placement="left"
            size="small"
            style="margin-bottom: 8px"
            :title="String(key)"
          >
            <n-descriptions-item label="Process">
              <n-text code>{{ target.process }}</n-text>
            </n-descriptions-item>
            <n-descriptions-item v-if="target.label_space" label="Label Space">
              <n-space size="small">
                <n-tag v-for="label in target.label_space" :key="label" size="small">{{ label }}</n-tag>
              </n-space>
            </n-descriptions-item>
            <n-descriptions-item v-if="target.threshold != null" label="Threshold">
              {{ target.threshold }}
            </n-descriptions-item>
          </n-descriptions>

          <template v-if="selectedPreset.runtime">
            <n-h3>Runtime</n-h3>
            <n-descriptions bordered :column="1" label-placement="left" size="small" style="margin-bottom: 16px">
              <n-descriptions-item label="GPU">
                {{ selectedPreset.runtime.gpu ? 'Required' : 'Not required' }}
              </n-descriptions-item>
              <n-descriptions-item v-if="selectedPreset.runtime.min_vram_gb" label="Min VRAM">
                {{ selectedPreset.runtime.min_vram_gb }} GB
              </n-descriptions-item>
              <n-descriptions-item v-if="selectedPreset.runtime.queue" label="Queue">
                <n-text code>{{ selectedPreset.runtime.queue }}</n-text>
              </n-descriptions-item>
            </n-descriptions>
          </template>

          <template v-if="selectedPreset.tags && selectedPreset.tags.length > 0">
            <n-h3>Tags</n-h3>
            <n-space size="small">
              <n-tag v-for="tag in selectedPreset.tags" :key="tag" size="small" type="success">{{ tag }}</n-tag>
            </n-space>
          </template>
        </template>
      </n-drawer-content>
    </n-drawer>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, h, computed } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { NTag } from "naive-ui";
import { api } from "../api";
import type { TrainingPreset } from "../types";
import { useOrgStore } from "../stores/org";

const orgStore = useOrgStore();

// ── query ───────────────────────────────────────────────────────────────────
const { data: presets, isLoading, isError, error } = useQuery({
  queryKey: computed(() => ["presets", orgStore.currentOrgId]),
  queryFn: api.listPresets,
  enabled: computed(() => !!orgStore.currentOrgId),
});

// ── detail drawer ───────────────────────────────────────────────────────────
const showDrawer = ref(false);
const selectedPreset = ref<TrainingPreset | null>(null);

function rowProps(row: TrainingPreset) {
  return {
    style: "cursor: pointer",
    onClick: () => {
      selectedPreset.value = row;
      showDrawer.value = true;
    },
  };
}

// ── table columns ───────────────────────────────────────────────────────────
const columns = [
  {
    title: "Name",
    key: "name",
    render: (row: TrainingPreset) =>
      h("span", { style: "font-weight: 500" }, row.name),
  },
  {
    title: "Framework",
    key: "framework",
    render: (row: TrainingPreset) =>
      h(NTag, { type: "info", size: "small" }, { default: () => row.model.framework }),
  },
  {
    title: "Base Model",
    key: "base_model",
    render: (row: TrainingPreset) =>
      h("span", {}, row.model.base_model),
  },
  {
    title: "Targets",
    key: "targets",
    render: (row: TrainingPreset) => {
      const keys = Object.keys(row.predict?.targets ?? {});
      return h(
        "span",
        {},
        keys.map((k) => h(NTag, { size: "small", style: "margin-right: 4px" }, { default: () => k }))
      );
    },
  },
  {
    title: "Version",
    key: "version",
    width: 100,
    render: (row: TrainingPreset) =>
      h("span", { style: "color: var(--n-text-color-3); font-size: 12px" }, row.version ?? "-"),
  },
  {
    title: "Status",
    key: "deprecated",
    width: 100,
    render: (row: TrainingPreset) =>
      row.deprecated
        ? h(NTag, { type: "warning", size: "small" }, { default: () => "Deprecated" })
        : h(NTag, { type: "success", size: "small" }, { default: () => "Active" }),
  },
];
</script>
